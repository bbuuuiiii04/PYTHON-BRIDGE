"""
Direct Rekordbox state reader.

Polls Rekordbox memory at ~30 Hz and emits direct ``BridgeEvent`` kinds
(``MASTER_CHANGED``, ``TRACK_LOADED``, ``PLAY``, ``PAUSE``, ``BPM_UPDATE``,
``ANLZ_PATH``). Runtime wiring can route selected event kinds from this reader
into the authoritative StateManager queue behind per-signal env flags and
readiness callbacks.

Architecture
------------
* One daemon thread, period = ``MEM_POLL_HZ // 2`` Hz (default 30 Hz).
* Reads through pointer chains from a per-version ``RBOffsetVersion`` table
  (see ``rb_offsets.py``), via ``mach_vm_read_overwrite`` (same primitive
  ``rb_memory.py`` already uses).
* Fail-closed: if the running RB version has no offsets in the table, or the
  RB pid / base address cannot be resolved, the thread logs once and exits.
* Diff against last-seen state to suppress duplicate events. Each emit carries
  ``source='rb_state'`` so downstream logs and fallback gates can distinguish
  direct memory events from OSC/MTC and bridge-local events.

Play / pause derivation
-----------------------
Playback is derived from the per-deck monotonic position field:
``is_playing = (current_samples != previous_samples)`` after warmup evidence.

Bridge-deck mapping
-------------------
RB has 4 decks A/B/C/D (0..3). The bridge has 2 decks (left=1, right=2).
Mapping is A/C → 1, B/D → 2.
"""
from __future__ import annotations

import logging
import math
import os
import queue
import re
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import MEM_POLL_HZ, RB_SCALE
from .active_deck_resolver import RB_MASTER_STALE_AFTER_S, label_low, label_upfader
from .models import BridgeEvent, Ev, MixerAuthoritySnapshot, MixerDeckReading
from .rb_memory import (
    PositionCache,
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
RB_MASTER_UNAVAILABLE_SOURCE = "unavailable"
DIRECT_AUTHORITY_LABEL = "direct_guarded"
ANLZ_DIRECT_ENV = "RBSS_ANLZ_DIRECT"
MASTER_DIRECT_ENV = "RBSS_MASTER_DIRECT"
PLAY_DIRECT_ENV = "RBSS_PLAY_DIRECT"
TRACK_LOAD_DIRECT_ENV = "RBSS_TRACK_LOAD_DIRECT"

# RB deck index (0..3) -> bridge deck (1 or 2).
def _bridge_deck(rb_idx: int) -> int:
    return (rb_idx % 2) + 1


# Whether the same BPM should be re-emitted.
_BPM_EMIT_THRESHOLD = 0.05
_PLAY_WARMUP_POLLS = 3
_LIVEPOS_LOG_INTERVAL_S = 5.0
_LIVEPOS_RESET_SAMPLES = 10_000   # below this after being above → track reset
_PLAY_EVIDENCE_POLLS = 2
RB_MASTER_REFRESH_INTERVAL_S = RB_MASTER_STALE_AFTER_S / 2.0
_TRACK_INFO_FIELD_RE = re.compile(r"(?:^|\n)\s*(?:[A-Za-z]\s+)?Title:\s*(.*?)(?:\r?\n|$)")


def extract_track_title(track_info: object) -> str:
    """Extract title text from RB's packed track-info buffer."""
    text = str(track_info or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    m = _TRACK_INFO_FIELD_RE.search(text)
    if m:
        return m.group(1).strip()
    return text


class RBStateReader(threading.Thread):
    """Daemon thread that emits BridgeEvents derived from direct RB memory reads.

    Instantiate, ``start()``, and consume events from the same queue
    ``StateManager`` already wires up.

    The instance is **safely a no-op** when offsets for the current RB version
    are missing — ``run()`` exits immediately without attaching to RB.
    """

    def __init__(
        self,
        event_queue: queue.Queue,
        offsets: Optional[RBOffsetVersion],
        *,
        authoritative_queue: Optional[queue.Queue] = None,
        authoritative_kinds: Optional[set[str] | frozenset[str]] = None,
        drop_unrouted_events: bool = False,
        shadow_logs_enabled: bool = True,
        rb_pid: Optional[int] = None,
        base_addr: Optional[int] = None,
        poll_hz: Optional[int] = None,
        position_cache: Optional[PositionCache] = None,
        anlz_available_callback: Optional[Callable[[int, bool], None]] = None,
        transport_available_callback: Optional[Callable[[int, bool], None]] = None,
        track_load_available_callback: Optional[Callable[[int, bool], None]] = None,
        master_available_callback: Optional[Callable[[bool], None]] = None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        super().__init__(name="rb-state-reader", daemon=True)
        self._q = event_queue
        self._authoritative_q = authoritative_queue
        self._authoritative_kinds = frozenset(authoritative_kinds or ())
        self._mixer_authority_enabled = Ev.MIXER_STATE in self._authoritative_kinds
        self._drop_unrouted_events = drop_unrouted_events
        self._shadow_logs_enabled = shadow_logs_enabled
        self._offs = offsets
        self._stop_event = threading.Event()
        hz = poll_hz if poll_hz is not None else max(1, MEM_POLL_HZ // 2)
        self._period = 1.0 / hz
        self._rb_pid = rb_pid
        self._base = base_addr
        self._clock = clock
        self._sleeper = sleeper
        self._pos_cache = position_cache
        self._anlz_available_callback = anlz_available_callback
        self._anlz_available_by_deck: dict[int, bool] = {}
        self._anlz_readable_this_tick: set[int] = set()
        self._transport_available_callback = transport_available_callback
        self._transport_available_by_deck: dict[int, bool] = {}
        self._transport_readable_this_tick: set[int] = set()
        self._track_load_available_callback = track_load_available_callback
        self._track_load_available_by_deck: dict[int, bool] = {}
        self._title_readable_this_tick: set[int] = set()
        self._master_available_callback = master_available_callback
        self._master_available: bool = False
        self._master_readable_this_tick: bool = False

        # Per-deck last-seen state for diffing
        self._last_master: Optional[int] = None
        self._last_master_event_key: Optional[tuple[object, ...]] = None
        self._last_master_event_at: float = 0.0
        self._last_track: dict[int, str] = {}
        self._last_bpm: dict[int, float] = {}
        self._last_pos_samples: dict[int, int] = {}
        self._last_playing: dict[int, bool] = {}
        self._valid_pos_polls: dict[int, int] = {}
        self._pending_playing: dict[int, bool] = {}
        self._pending_playing_count: dict[int, int] = {}
        self._last_anlz: dict[int, str] = {}
        self._last_livepos_log: dict[int, float] = {}

    def stop(self) -> None:
        self._stop_event.set()
        self._set_all_anlz_unavailable()
        self._set_all_transport_unavailable()
        self._set_all_track_load_unavailable()
        self._set_all_master_unavailable()

    # ── Thread entry ─────────────────────────────────────────────────────────
    def run(self) -> None:
        if os.getenv(_RB_STATE_DISABLE_ENV):
            log.info("RBStateReader disabled via %s", _RB_STATE_DISABLE_ENV)
            self._set_all_anlz_unavailable()
            self._set_all_transport_unavailable()
            self._set_all_track_load_unavailable()
            self._set_all_master_unavailable()
            return
        if self._offs is None:
            log.info("RBStateReader: no offsets for current RB version; not starting")
            self._set_all_anlz_unavailable()
            self._set_all_transport_unavailable()
            self._set_all_track_load_unavailable()
            self._set_all_master_unavailable()
            return
        try:
            task, base = self._attach()
        except Exception:
            log.exception("RBStateReader: attach failed; direct events unavailable")
            self._set_all_anlz_unavailable()
            self._set_all_transport_unavailable()
            self._set_all_track_load_unavailable()
            self._set_all_master_unavailable()
            return
        log.info("RBStateReader: attached pid=%s base=0x%x version=%s",
                 self._rb_pid, base, self._offs.version)

        next_tick = self._clock()
        while not self._stop_event.is_set():
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
        self._set_all_anlz_unavailable()
        self._set_all_transport_unavailable()
        self._set_all_track_load_unavailable()
        self._set_all_master_unavailable()

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
        self._anlz_readable_this_tick = set()
        self._transport_readable_this_tick = set()
        self._title_readable_this_tick = set()
        self._master_readable_this_tick = False

        now = self._clock()
        master_raw = self._follow_u8(task, base, offs.master_deck)
        if master_raw is not None:
            self._master_readable_this_tick = True
        if self._mixer_authority_enabled:
            self._publish_mixer_master_state(master_raw, offs, now)
        elif master_raw is not None and master_raw != self._last_master:
            self._last_master = master_raw
            if 0 <= master_raw < offs.deck_count and self._raw_deck_supports_resolver(master_raw):
                self._enqueue(BridgeEvent(
                    kind=Ev.MASTER_CHANGED,
                    deck=_bridge_deck(master_raw),
                    payload={"rb_raw_deck": master_raw},
                    source='rb_state',
                ))

        if self._mixer_authority_enabled:
            self._tick_mixer(task, base)

        for d in range(offs.deck_count):
            self._tick_deck(task, base, d)
        self._update_anlz_available()
        self._update_transport_available()
        self._update_track_load_available()
        self._update_master_available()

    def _publish_mixer_master_state(
        self,
        master_raw: Optional[int],
        offs: RBOffsetVersion,
        now: float,
    ) -> None:
        if master_raw is None:
            self._publish_master_invalid("unreadable", None, now)
            return

        self._last_master = master_raw
        if master_raw in (0, 1):
            key = ("valid", master_raw)
            if (
                key == self._last_master_event_key
                and now - self._last_master_event_at < RB_MASTER_REFRESH_INTERVAL_S
            ):
                return
            self._last_master_event_key = key
            self._last_master_event_at = now
            self._enqueue(BridgeEvent(
                kind=Ev.MASTER_CHANGED,
                deck=_bridge_deck(master_raw),
                payload={"rb_raw_deck": master_raw},
                source='rb_state',
            ))
            return

        if 0 <= master_raw < offs.deck_count:
            self._publish_master_invalid("unsupported_raw_deck", master_raw, now)
            return

        self._publish_master_invalid("no_master", master_raw, now)

    def _publish_master_invalid(
        self,
        reason: str,
        rb_raw_deck: Optional[int],
        now: float,
    ) -> None:
        key = ("invalid", reason, rb_raw_deck)
        if key == self._last_master_event_key:
            return
        self._last_master_event_key = key
        self._last_master_event_at = now
        payload = {"reason": reason}
        if rb_raw_deck is not None:
            payload["rb_raw_deck"] = rb_raw_deck
        self._enqueue(BridgeEvent(
            kind=Ev.MASTER_CHANGED,
            deck=0,
            payload=payload,
            source='rb_state',
        ))

    def _tick_deck(self, task: int, base: int, d: int) -> None:
        offs = self._offs
        assert offs is not None
        bridge = _bridge_deck(d)

        # ANLZ path must be observed before TRACK_LOADED so StateManager
        # consumes the fresh path for the same load generation.
        anlz = self._follow_pointer_string(task, base, offs.anlz_path_per_deck[d])
        prev_anlz = self._last_anlz.get(d)
        if anlz != prev_anlz:
            self._last_anlz[d] = anlz or ""
            if anlz:
                self._anlz_readable_this_tick.add(bridge)
                if self._shadow_logs_enabled or Ev.ANLZ_PATH in self._authoritative_kinds:
                    log.info("[ANLZ][DIRECT] deck=%d path=%s", bridge, anlz)
                self._enqueue(BridgeEvent(
                    kind=Ev.ANLZ_PATH,
                    deck=bridge,
                    payload={'anlz_path': anlz},
                    source='rb_state',
                ))
        elif anlz:
            self._anlz_readable_this_tick.add(bridge)

        # Track-info string from RB's packed 500-byte buffer.
        track_info = self._follow_string(task, base, offs.track_info_per_deck[d], 500)
        if track_info is not None:
            if track_info:
                self._title_readable_this_tick.add(bridge)
            title = extract_track_title(track_info)
            if title and title != self._last_track.get(d):
                self._last_track[d] = title
                if self._shadow_logs_enabled or Ev.TRACK_LOADED in self._authoritative_kinds:
                    log.info("[TITLE][DIRECT] deck=%d title=%r", bridge, title)
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
        if self._mixer_authority_enabled and not self._raw_deck_supports_resolver(d):
            return
        pos = self._follow_i64(task, base, offs.live_pos_per_deck[d])
        if pos is None:
            self._reset_play_inference(d)
            return
        self._transport_readable_this_tick.add(bridge)
        prev = self._last_pos_samples.get(d)
        self._last_pos_samples[d] = pos
        self._valid_pos_polls[d] = self._valid_pos_polls.get(d, 0) + 1

        # LIVEPOS shadow log — A3 evidence.
        # Log every _LIVEPOS_LOG_INTERVAL_S or on apparent track reset.
        # Compares chain-derived elapsed_ms against PositionCache for parity.
        _now = self._clock()
        _reset = (prev is not None
                  and prev > _LIVEPOS_RESET_SAMPLES
                  and 0 <= pos < _LIVEPOS_RESET_SAMPLES)
        if _reset or (_now - self._last_livepos_log.get(d, 0.0)) >= _LIVEPOS_LOG_INTERVAL_S:
            self._last_livepos_log[d] = _now
            _elapsed_ms = int(pos * RB_SCALE) if pos >= 0 else -1
            _snap = self._pos_cache.get(bridge) if self._pos_cache is not None else None
            _cache_ms = _snap.elapsed_ms if _snap is not None else None
            _delta_ms = (_elapsed_ms - _cache_ms) if (_elapsed_ms >= 0 and _cache_ms is not None) else None
            if self._shadow_logs_enabled:
                log.info(
                    "[LIVEPOS][DIRECT] deck=%d samples=%d elapsed_ms=%d "
                    "cache_ms=%s delta_ms=%s%s",
                    bridge, pos, _elapsed_ms,
                    str(_cache_ms) if _cache_ms is not None else "none",
                    ("%+d" % _delta_ms) if _delta_ms is not None else "none",
                    " [reset]" if _reset else "",
                )

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
            if is_playing:
                self._enqueue(BridgeEvent(
                    kind=Ev.PLAY,
                    deck=bridge,
                    payload={"rb_raw_deck": d},
                    source='rb_state',
                ))
            return
        if was_playing != is_playing:
            self._last_playing[d] = is_playing
            self._enqueue(BridgeEvent(
                kind=Ev.PLAY if is_playing else Ev.PAUSE,
                deck=bridge,
                payload={"rb_raw_deck": d},
                source='rb_state',
            ))

    def _raw_deck_supports_resolver(self, rb_idx: int) -> bool:
        return not self._mixer_authority_enabled or rb_idx in (0, 1)

    def _tick_mixer(self, task: int, base: int) -> None:
        offs = self._offs
        assert offs is not None
        now = self._clock()
        chains = (
            offs.mixer_deck1_upfader_raw,
            offs.mixer_deck2_upfader_raw,
            offs.mixer_deck1_low_raw,
            offs.mixer_deck2_low_raw,
        )
        if any(ch is None for ch in chains):
            snapshot = MixerAuthoritySnapshot(
                valid=False,
                deck={},
                updated_at=now,
                reason="missing_offsets",
            )
            self._enqueue(BridgeEvent(Ev.MIXER_STATE, 0, {"snapshot": snapshot}, "rb_state"))
            return

        reads = (
            self._follow_finite_f32_result(task, base, chains[0], minimum=0.0, maximum=1023.0),
            self._follow_finite_f32_result(task, base, chains[1], minimum=0.0, maximum=1023.0),
            self._follow_finite_f32_result(task, base, chains[2], minimum=0.0, maximum=255.0),
            self._follow_finite_f32_result(task, base, chains[3], minimum=0.0, maximum=255.0),
        )
        invalid_reason = next((reason for value, reason in reads if value is None), "")
        if invalid_reason:
            snapshot = MixerAuthoritySnapshot(
                valid=False,
                deck={},
                updated_at=now,
                reason=invalid_reason,
            )
            self._enqueue(BridgeEvent(Ev.MIXER_STATE, 0, {"snapshot": snapshot}, "rb_state"))
            return

        d1_up, d2_up, d1_low, d2_low = (value for value, _ in reads)
        assert d1_up is not None and d2_up is not None and d1_low is not None and d2_low is not None
        deck = {
            1: self._mixer_reading(1, d1_up, d1_low),
            2: self._mixer_reading(2, d2_up, d2_low),
        }
        snapshot = MixerAuthoritySnapshot(
            valid=True,
            deck=deck,
            updated_at=now,
            reason="ok",
        )
        self._enqueue(BridgeEvent(Ev.MIXER_STATE, 0, {"snapshot": snapshot}, "rb_state"))

    def _mixer_reading(self, deck: int, up_raw: float, low_raw: float) -> MixerDeckReading:
        up_norm = up_raw / 1023.0
        low_norm = low_raw / 255.0
        return MixerDeckReading(
            deck=deck,
            upfader_raw=up_raw,
            upfader_norm=up_norm,
            upfader_label=label_upfader(up_norm),
            low_raw=low_raw,
            low_norm=low_norm,
            low_label=label_low(low_norm),
        )

    def _reset_play_inference(self, d: int) -> None:
        self._last_pos_samples.pop(d, None)
        self._last_playing.pop(d, None)
        self._valid_pos_polls[d] = 0
        self._pending_playing.pop(d, None)
        self._pending_playing_count.pop(d, None)

    def _update_anlz_available(self) -> None:
        if Ev.ANLZ_PATH not in self._authoritative_kinds:
            return
        for bridge in (1, 2):
            self._set_anlz_available(bridge, bridge in self._anlz_readable_this_tick)

    def _set_all_anlz_unavailable(self) -> None:
        for bridge in (1, 2):
            self._set_anlz_available(bridge, False)

    def _set_anlz_available(self, deck: int, available: bool) -> None:
        if self._anlz_available_by_deck.get(deck, False) == available:
            return
        self._anlz_available_by_deck[deck] = available
        if self._anlz_available_callback is None:
            return
        try:
            self._anlz_available_callback(deck, available)
        except Exception:
            log.debug("RBStateReader ANLZ availability callback failed", exc_info=True)

    def _update_transport_available(self) -> None:
        if Ev.PLAY not in self._authoritative_kinds and Ev.PAUSE not in self._authoritative_kinds:
            return
        offs = self._offs
        if offs is None:
            self._set_all_transport_unavailable()
            return
        ready_decks: set[int] = set()
        raw_range = range(2) if self._mixer_authority_enabled else range(offs.deck_count)
        for d in raw_range:
            bridge = _bridge_deck(d)
            if bridge in self._transport_readable_this_tick and d in self._last_playing:
                ready_decks.add(bridge)
        for bridge in (1, 2):
            self._set_transport_available(bridge, bridge in ready_decks)

    def _set_all_transport_unavailable(self) -> None:
        for bridge in (1, 2):
            self._set_transport_available(bridge, False)

    def _set_transport_available(self, deck: int, available: bool) -> None:
        previous = self._transport_available_by_deck.get(deck, False)
        if previous == available:
            return
        self._transport_available_by_deck[deck] = available
        if previous and not available and self._mixer_authority_enabled:
            self._enqueue(BridgeEvent(
                kind=Ev.PAUSE,
                deck=deck,
                payload={"reason": "transport_unavailable"},
                source='rb_state',
            ))
        if self._transport_available_callback is None:
            return
        try:
            self._transport_available_callback(deck, available)
        except Exception:
            log.debug("RBStateReader transport availability callback failed", exc_info=True)

    def _update_track_load_available(self) -> None:
        if Ev.TRACK_LOADED not in self._authoritative_kinds:
            return
        for bridge in (1, 2):
            self._set_track_load_available(bridge, bridge in self._title_readable_this_tick)

    def _set_all_track_load_unavailable(self) -> None:
        for bridge in (1, 2):
            self._set_track_load_available(bridge, False)

    def _set_track_load_available(self, deck: int, available: bool) -> None:
        if self._track_load_available_by_deck.get(deck, False) == available:
            return
        self._track_load_available_by_deck[deck] = available
        if self._track_load_available_callback is None:
            return
        try:
            self._track_load_available_callback(deck, available)
        except Exception:
            log.debug("RBStateReader track_load availability callback failed", exc_info=True)

    def _update_master_available(self) -> None:
        if Ev.MASTER_CHANGED not in self._authoritative_kinds:
            return
        offs = self._offs
        ready = (
            offs is not None
            and self._master_readable_this_tick
            and self._last_master is not None
            and 0 <= self._last_master < offs.deck_count
            and self._raw_deck_supports_resolver(self._last_master)
        )
        self._set_master_available(ready)

    def _set_all_master_unavailable(self) -> None:
        self._set_master_available(False)

    def _set_master_available(self, available: bool) -> None:
        if self._master_available == available:
            return
        self._master_available = available
        if self._master_available_callback is None:
            return
        try:
            self._master_available_callback(available)
        except Exception:
            log.debug("RBStateReader master availability callback failed", exc_info=True)

    # ── Queue helper ─────────────────────────────────────────────────────────
    def _enqueue(self, ev: BridgeEvent) -> None:
        if ev.kind in self._authoritative_kinds:
            target = self._authoritative_q or self._q
        elif self._drop_unrouted_events:
            return
        else:
            target = self._q
        try:
            target.put_nowait(ev)
        except queue.Full:
            # Drop on overflow rather than blocking the reader thread.
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
        # Filter out NaN / inf / nonsense; suppress rather than synthesise.
        if not (0.0 < v < 1000.0):
            return None
        return v

    def _follow_finite_f32(
        self,
        task: int,
        base: int,
        ch: ChainEntry,
        *,
        minimum: float,
        maximum: float,
    ) -> Optional[float]:
        value, _reason = self._follow_finite_f32_result(
            task,
            base,
            ch,
            minimum=minimum,
            maximum=maximum,
        )
        return value

    def _follow_finite_f32_result(
        self,
        task: int,
        base: int,
        ch: ChainEntry,
        *,
        minimum: float,
        maximum: float,
    ) -> tuple[Optional[float], str]:
        addr = self._follow_addr(task, base, ch)
        if addr is None:
            return None, "unreadable"
        try:
            data = _read_bytes(task, addr, 4)
        except OSError:
            return None, "unreadable"
        value = struct.unpack_from("<f", data)[0]
        if not math.isfinite(value):
            return None, "non_finite"
        if not (minimum <= value <= maximum):
            return None, "out_of_range"
        return value, "ok"

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

    def _follow_pointer_string(self, task: int, base: int, ch: ChainEntry,
                               max_len: int = 512) -> Optional[str]:
        """Walk the chain, read the pointer stored at the endpoint, read the string there.

        ANLZ chains use this format: the final address holds a u64 pointer to
        the NUL-terminated path string, rather than the string bytes directly.
        Returns None on null pointer, unreadable chain, or decode failure.
        """
        addr = self._follow_addr(task, base, ch)
        if addr is None:
            return None
        try:
            ptr_bytes = _read_bytes(task, addr, 8)
        except OSError:
            return None
        str_ptr = struct.unpack_from("<Q", ptr_bytes)[0]
        if str_ptr == 0:
            return None
        try:
            data = _read_bytes(task, str_ptr, max_len)
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
                 "authority=%s",
                 rb_version or "<unknown>", DIRECT_AUTHORITY_LABEL)
        return DirectMasterStatus(
            attempted=True,
            supported=False,
            available=False,
            readable=False,
            source=RB_MASTER_UNAVAILABLE_SOURCE,
            reason="unsupported_version",
            rb_version=rb_version,
        )

    reader = RBStateReader(queue.Queue(maxsize=1), offs, rb_pid=rb_pid, base_addr=base_addr)
    try:
        task, base = reader._attach()
    except Exception as exc:
        log.info("[RBMASTER][DIRECT] attempted=1 supported_version=1 readable=0 "
                 "version=%s direct_master=unavailable fail_closed_reason=attach_failed "
                 "detail=%s authority=%s",
                 offs.version,
                 exc,
                 DIRECT_AUTHORITY_LABEL)
        return DirectMasterStatus(
            attempted=True,
            supported=True,
            available=False,
            readable=False,
            source=RB_MASTER_UNAVAILABLE_SOURCE,
            reason="attach_failed",
            rb_version=offs.version,
        )

    master_raw = reader._follow_u8(task, base, offs.master_deck)
    if master_raw is None:
        log.info("[RBMASTER][DIRECT] attempted=1 supported_version=1 readable=0 "
                 "version=%s direct_master=unavailable fail_closed_reason=unreadable "
                 "authority=%s",
                 offs.version,
                 DIRECT_AUTHORITY_LABEL)
        return DirectMasterStatus(
            attempted=True,
            supported=True,
            available=False,
            readable=False,
            source=RB_MASTER_UNAVAILABLE_SOURCE,
            reason="unreadable",
            rb_version=offs.version,
            pid=reader._rb_pid,
            base=base,
        )

    bridge_deck = _bridge_deck(master_raw) if 0 <= master_raw < offs.deck_count else None
    reason = "ok" if bridge_deck is not None else "no_master"
    log.info("[RBMASTER][DIRECT] attempted=1 supported_version=1 readable=1 "
             "version=%s raw=%d direct_master=%s reason=%s source=%s authority=%s",
             offs.version, master_raw, direct_master_label(bridge_deck), reason,
             RB_MASTER_DIRECT_SOURCE, DIRECT_AUTHORITY_LABEL)
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
            source=RB_MASTER_UNAVAILABLE_SOURCE,
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


# ── Convenience constructor ──────────────────────────────────────────────────

def make_rb_state_reader(
    event_queue: queue.Queue,
    rb_version: str,
    **kwargs,
) -> RBStateReader:
    """Construct an RBStateReader for the current RB version.

    The returned reader is a no-op (run() exits immediately) when
    ``rb_version`` is unsupported.
    """
    offsets = load_offsets_for_version(rb_version)
    if offsets is None:
        log.info("RBStateReader: RB version %r not in offset table; reader will be a no-op",
                 rb_version)
    return RBStateReader(event_queue, offsets, **kwargs)
