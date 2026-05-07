"""
StateManager — authoritative state + 200 Hz push loop.

Single event-loop thread:
  - drains event_queue at the top of every tick
  - reads PositionCache for current position
  - drives beat emission and OS2L sends
  - handles deck switches, arm/clear, play/stop

All DeckState writes happen in this thread. No external locks on DeckState.

Section map:
  StateManager.__init__
  StateManager.start / stop
  StateManager._run           — main loop
  StateManager._handle_event  — event dispatch
  StateManager._push_tick     — 200 Hz beat/position logic
  arm / unarm helpers
  stop / resume helpers
"""
from __future__ import annotations

import bisect
import logging
import math
import os as _os
import queue
import threading
import time
from typing import Optional

from .config import (
    AUTOLOOP_ARM_PHRASE_BEATS, AUTOLOOP_BEATS, ARM_GUARD_S, STOP_DEBOUNCE_S,
    PLAY_SETTLE_MS, TIMING_COMPENSATION_MS,
    BPM_THRESHOLD_SCRIPTED, BPM_THRESHOLD_UNSCRIPTED,
    MEM_STALE_S,
)
from .models import ArmSequence, BridgeEvent, DeckState, Ev, OutputState, PositionSnapshot, TrackMetadata
from .osl_output import OS2LOutput
from .rb_memory import PositionCache
from .scripted_tracks import SCRIPTED_TRACKS, lookup as st_lookup
from .logging_manager import get_logging_manager

log = logging.getLogger("state_manager")
LOG = get_logging_manager()

_LATENCY_WARN_MS = 50.0
_TC_LATENCY_WARN_MS = 250.0
_AUTOLOOP_IDLE_DEBOUNCE_S = max(STOP_DEBOUNCE_S, 2.0)
LIVE_BPM_FOLLOW_ENV = "RBSS_LIVE_BPM_FOLLOW"
AUTOLOOP_MASTER_PHRASE_ARM_ENV = "RBSS_AUTOLOOP_MASTER_PHRASE_ARM"
_LIVE_BPM_FOLLOW_THRESHOLD = BPM_THRESHOLD_UNSCRIPTED
_LIVE_BPM_FOLLOW_SEND_INTERVAL_S = 0.10
_AUTOLOOP_MASTER_PHRASE_START_GRACE_BEATS = 0.5
_AUTOLOOP_PHRASE_LATE_TOLERANCE_MS = 125
_AUTOLOOP_PHRASE_MIN_RUNWAY_MS = 1000


# ── Beat position helper ──────────────────────────────────────────────────────

def _compute_beat_pos(elapsed_ms: float, bpm: float, first_beat_ms: float = 0.0) -> float:
    """Fractional beat position within current bar.

    Returns 0.0 if bpm == 0. Negative means before first beat.
    """
    if bpm <= 0:
        return 0.0
    beat_ms = 60_000.0 / bpm
    offset = elapsed_ms - first_beat_ms
    pos = math.fmod(offset / beat_ms, 4.0)
    return pos if pos >= 0 else pos + 4.0


def _compute_beatgrid_position(
    elapsed_ms: float,
    beatgrid_times_ms: list[float],
) -> Optional[tuple[float, float]]:
    """Return (wrapped_0_to_4, absolute) beat position from ordered grid markers."""
    if len(beatgrid_times_ms) < 2:
        return None

    times = beatgrid_times_ms
    idx = bisect.bisect_right(times, elapsed_ms) - 1
    if idx < 0:
        interval = times[1] - times[0]
        if interval <= 0:
            return None
        abs_pos = (elapsed_ms - times[0]) / interval
    elif idx >= len(times) - 1:
        interval = times[-1] - times[-2]
        if interval <= 0:
            return None
        abs_pos = (len(times) - 1) + ((elapsed_ms - times[-1]) / interval)
    else:
        interval = times[idx + 1] - times[idx]
        if interval <= 0:
            return None
        abs_pos = idx + ((elapsed_ms - times[idx]) / interval)

    wrapped = math.fmod(abs_pos, 4.0)
    if wrapped < 0:
        wrapped += 4.0
    return wrapped, abs_pos


def _beatgrid_elapsed_for_abs_beat(
    abs_beat: int,
    beatgrid_times_ms: list[float],
) -> Optional[tuple[int, str]]:
    """Return (elapsed_ms, source) for an absolute beat target from grid markers."""
    if len(beatgrid_times_ms) < 2:
        return None

    target = int(abs_beat)
    times = beatgrid_times_ms
    if 0 <= target < len(times):
        return int(round(times[target])), "grid"

    interval = times[-1] - times[-2]
    if interval <= 0:
        return None
    elapsed_ms = times[-1] + ((target - (len(times) - 1)) * interval)
    return int(round(elapsed_ms)), "grid-extrapolated"


class StateManager:
    """Central state machine.

    Create, then call start(). The event loop and push loop share one thread
    so DeckState is never accessed concurrently.
    """

    _TICK_INTERVAL = 1.0 / 200   # 200 Hz

    def __init__(
        self,
        event_queue:    queue.Queue[BridgeEvent],
        position_cache: PositionCache,
        output:         OS2LOutput,
        live_bpm=None,
        live_bpm_follow: Optional[bool] = None,
    ) -> None:
        self._eq    = event_queue
        self._cache = position_cache
        self._out   = output
        self._live_bpm = live_bpm
        self._live_bpm_follow = (
            _os.environ.get(LIVE_BPM_FOLLOW_ENV, "1") != "0"
            if live_bpm_follow is None else live_bpm_follow
        )
        self._autoloop_master_phrase_arm = (
            _os.environ.get(AUTOLOOP_MASTER_PHRASE_ARM_ENV, "1") != "0"
        )
        self._stop  = threading.Event()

        # Per-deck state (written only by this thread after start())
        self._deck: dict[int, DeckState] = {
            1: DeckState(number=1),
            2: DeckState(number=2),
        }
        # Push-loop bookkeeping
        self._os = OutputState()

        # Arm debounce: (track_id, deck) → last arm time
        self._arm_times: dict[tuple, float] = {}

        # FM-3: initialize resolver and pending arm before any events arrive
        self._resolver = None
        self._pending_arm: Optional[ArmSequence] = None

        # Rate-limited position logging (once every 5 s per deck)
        self._last_pos_log: dict[int, float] = {1: 0.0, 2: 0.0}

        # TL TC fallback: (elapsed_ms, wall_time, pitch_factor) per deck
        # Updated by TC_UPDATE events. pitch_factor from ENGINE STATE pitch% field.
        self._tl_tc: dict[int, tuple[int, float, float]] = {1: (0, 0.0, 1.0), 2: (0, 0.0, 1.0)}

        # ANLZ path keyed by bridge deck: populated by ANLZ_PATH event,
        # consumed by _on_track_loaded to skip lsof
        self._pending_anlz_path: dict[int, str] = {}

        # Guards stale lsof results: each TRACK_LOADED increments this per deck
        # FilepathResolver echoes load_gen back in FILEPATH_RESOLVED
        # (already stored in DeckState.load_gen)

        # Tracks which deck most recently received a TRACK_LOADED event.
        # Updated by _on_track_loaded; read by OSC handler to route SCRIPTED_ARM.
        self._last_loaded_deck: int = 0

        # Per deck trace/timing for TRACK_LOADED -> FILEPATH_RESOLVED.
        self._load_trace: dict[int, str] = {}
        self._load_mono: dict[int, float] = {}

    def set_initial_state(self, active_deck: int, source: str = "TL ENGINE STATE") -> None:
        """Apply startup state read from TL ENGINE STATE before event loop starts."""
        if active_deck in (1, 2):
            self._os.active_deck = active_deck
            log.info("StateManager: initial active_deck=%d (from %s)", active_deck, source)

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self._run, name="state-manager", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()

    def get_active_deck(self) -> int:
        return self._os.active_deck

    def get_last_loaded_deck(self) -> int:
        """Deck that most recently received a TRACK_LOADED event (1 or 2; 0 if none yet)."""
        return self._last_loaded_deck

    def get_deck_elapsed_ms(self, deck: int) -> Optional[int]:
        """Best current elapsed estimate for memory-side provisional discovery.

        This is a read-only hint for RBMemoryReader. StateManager remains the
        authority for TL/MTC synthesis; the memory reader only uses this value
        to find paused Deck-2 candidates and still requires movement validation
        before publishing memory snapshots.
        """
        if deck not in (1, 2):
            return None
        d = self._deck[deck]
        tl_ms, tl_at, tl_pitch = self._tl_tc.get(deck, (0, 0.0, 1.0))
        now = time.monotonic()
        if tl_ms > 0 and 0.0 < now - tl_at < 45.0:
            age_ms = (now - tl_at) * 1000.0 * tl_pitch
            return int(tl_ms + (age_ms if d.playing else 0.0))
        if d.elapsed_ms > 0:
            return d.elapsed_ms
        return None

    def get_deck_playing(self, deck: int) -> bool:
        """TL-authoritative play state hint for memory-side discovery scheduling."""
        if deck not in (1, 2):
            return False
        return self._deck[deck].playing

    # ── Main loop ────────────────────────────────────────────────────────────

    def _run(self) -> None:
        log.info("StateManager: starting")
        while not self._stop.is_set():
            t0 = time.monotonic()
            self._drain_events()
            self._push_tick()
            remaining = self._TICK_INTERVAL - (time.monotonic() - t0)
            if remaining > 0:
                time.sleep(remaining)

    def _drain_events(self) -> None:
        """Consume all pending events without blocking."""
        while True:
            try:
                ev = self._eq.get_nowait()
            except queue.Empty:
                break
            try:
                payload = ev.payload or {}
                anomaly = LOG.detect_anomaly(ev)
                with LOG.event_scope(
                    ev.kind,
                    deck=ev.deck,
                    source=ev.source,
                    trace_id=str(payload.get("__trace_id", "")),
                    anomaly=anomaly,
                ):
                    self._handle_event(ev)
                    latency_ms, prev = LOG.finish_event(ev)
                    warn_ms = _TC_LATENCY_WARN_MS if ev.kind == Ev.TC_UPDATE else _LATENCY_WARN_MS
                    if latency_ms > warn_ms:
                        log.warning("event latency %.1fms kind=%s", latency_ms, ev.kind)
                    elif log.isEnabledFor(logging.DEBUG):
                        if prev and prev.kind != ev.kind:
                            delta_ms = (time.monotonic() - prev.mono) * 1000.0
                            log.debug("event relation: %s deck%d %.1fms after %s deck%d",
                                      ev.kind, ev.deck, delta_ms, prev.kind, prev.deck)
                        log.debug("event processed %.1fms kind=%s", latency_ms, ev.kind)
            except Exception:
                LOG.log_error(log, "StateManager: error handling %s", ev.kind,
                              payload=getattr(ev, "payload", {}), exc_info=True)

    # ── Event dispatch ────────────────────────────────────────────────────────

    def _handle_event(self, ev: BridgeEvent) -> None:
        payload = {k: v for k, v in ev.payload.items() if not k.startswith("__")}
        log.debug("event received kind=%s src=%s payload=%s", ev.kind, ev.source, payload)
        d = ev.deck

        if ev.kind == Ev.MASTER_CHANGED:
            self._on_master_changed(d, ev.source)

        elif ev.kind == Ev.TRACK_LOADED:
            self._on_track_loaded(d, ev.payload.get("title", ""), ev)

        elif ev.kind == Ev.PLAY:
            if not self._deck[d].playing:
                log.info("[D%d] playing", d)
            self._deck[d].playing = True

        elif ev.kind == Ev.PAUSE:
            if self._deck[d].playing:
                log.info("[D%d] paused", d)
            self._deck[d].playing = False
            if d == self._os.active_deck:
                self._os.play_settle_after = 0.0

        elif ev.kind == Ev.FILEPATH_RESOLVED:
            self._on_filepath_resolved(d, ev.payload)

        elif ev.kind == Ev.ANLZ_PATH:
            # Store ANLZ path; consumed by next TRACK_LOADED for this deck
            self._pending_anlz_path[ev.deck] = ev.payload.get('anlz_path', '')

        elif ev.kind == Ev.TC_UPDATE:
            tc_ms = ev.payload.get('elapsed_ms', 0)
            if tc_ms > 0:
                pitch = ev.payload.get('pitch_factor', 1.0)
                self._tl_tc[ev.deck] = (tc_ms, ev.mono, pitch)

        elif ev.kind == Ev.BPM_UPDATE:
            # ENGINE STATE fires every ~15s with live pitch-adjusted BPM
            d = self._deck[ev.deck]
            new_bpm = ev.payload.get('bpm', 0.0)
            if self._live_bpm is not None and new_bpm > 0:
                try:
                    self._live_bpm.update_hint(ev.deck, new_bpm, d.meta.bpm)
                except Exception:
                    log.debug("live BPM hint update failed", exc_info=True)
            if new_bpm > 0 and abs(new_bpm - d.meta.bpm) > 0.5:
                log.debug("bpm_update deck %d: %.1f → %.1f", ev.deck, d.meta.bpm, new_bpm)
                d.meta.bpm = new_bpm

        elif ev.kind == Ev.SCRIPTED_ARM:
            sid = ev.payload.get("scripted_id", 0)
            if sid:
                d_obj = self._deck[d]
                if d_obj.scripted_id != sid:
                    d_obj.scripted_id = sid
                    # If OSC arrived after the deck switch already armed the wrong show,
                    # reset lighting_mode so the machine re-arms with the correct id.
                    if d == self._os.active_deck and self._os.lighting_mode == "scripted":
                        self._os.lighting_mode = ""

        elif ev.kind == Ev.SCRIPTED_CLEAR:
            self._arm_unscripted(d)

        elif ev.kind == Ev.RB_RESTARTED:
            # FM-11: force stop immediately — don't wait for stale detection
            log.info("[RB] restarted (pid=%d) — forcing stop", ev.payload.get("pid", 0))
            self._pending_arm = None
            for d in self._deck.values():
                d.playing = False
                d.scripted_id = 0
            if self._os.was_playing:
                self._do_stop(self._os.active_deck, self._os.last_beat_elapsed_ms)
            self._os.was_playing = False
            self._os.not_playing_since = 0.0
            # Reset lighting state machine so it re-derives on next tick without debounce.
            self._os.lighting_mode    = "idle"
            self._os.lighting_desired = "idle"
            self._os.lighting_stable_since = 0.0
            self._os.autoloop_arm_bpm = 0.0
            self._os.autoloop_arm_deck = 0
            self._os.last_autoloop_status_phrase_beat = 0
            self._clear_autoloop_arm_phrase_lock()
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_pending_autoloop_master_phrase_arm()
            if self._live_bpm is not None:
                try:
                    self._live_bpm.invalidate()
                except Exception:
                    log.debug("live BPM invalidation failed", exc_info=True)

    # ── Deck switch ───────────────────────────────────────────────────────────

    def _on_master_changed(self, new_deck: int, source: str) -> None:
        old_deck = self._os.active_deck
        if new_deck == old_deck:
            return
        log.info("MASTER_CHANGED deck%d -> deck%d reason=%s", old_deck, new_deck, source)
        LOG.stats.record_transition(new_deck, "master")
        # OSC race fix: TL's /bridge/active_deck can arrive after /bridge/track_loaded,
        # so SCRIPTED_ARM may land on the old active deck. If old deck wasn't playing
        # and new deck has no scripted_id, transfer it.
        old_d = self._deck[old_deck]
        new_d = self._deck[new_deck]
        if (
            _os.environ.get("RBSS_SCRIPTED_DIRECT") != "1"
            and old_d.scripted_id > 0
            and new_d.scripted_id == 0
            and not old_d.playing
        ):
            log.debug("[D%d→D%d] transferring scripted_id=%d (OSC/switch race)",
                      old_deck, new_deck, old_d.scripted_id)
            new_d.scripted_id = old_d.scripted_id
            old_d.scripted_id = 0
        self._os.active_deck = new_deck
        self._os.last_arm_mono = time.monotonic()
        self._os.push_reset_bpm = True
        # Force lighting re-evaluation for the new master on the next tick.
        # Reset both lighting_mode and lighting_desired so the mode transition
        # always fires even when both old and new master have scripted tracks.
        self._os.lighting_mode    = ""
        self._os.lighting_desired = ""
        self._os.lighting_stable_since = 0.0
        # Reset push-loop play state so old deck's was_playing doesn't trigger
        # an immediate stale force-stop on the new active deck.
        self._os.was_playing = False
        self._os.play_settle_after = 0.0
        self._os.not_playing_since = 0.0
        self._os.autoloop_arm_bpm = 0.0
        self._os.autoloop_arm_deck = 0
        self._os.last_autoloop_status_phrase_beat = 0
        self._os.autoloop_arm_after_master_change = True
        self._os.autoloop_master_change_source = source
        self._clear_autoloop_arm_phrase_lock()
        self._clear_live_bpm_follow()
        self._clear_autoloop_tempo_relock()
        self._clear_pending_autoloop_master_phrase_arm()

    # ── Track load → lsof trigger ─────────────────────────────────────────────

    def _on_track_loaded(self, deck: int, title: str, ev: BridgeEvent) -> None:
        d = self._deck[deck]
        d.meta.clear()
        d.scripted_id = 0
        d.load_gen += 1
        if deck == self._os.active_deck:
            self._clear_autoloop_arm_phrase_lock()
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_pending_autoloop_master_phrase_arm()
        d.tl_title = title
        self._last_loaded_deck = deck
        trace_id = str(ev.payload.get("__trace_id", ""))
        if trace_id:
            self._load_trace[deck] = trace_id
        self._load_mono[deck] = time.monotonic()
        log.info("TRACK_LOADED title=%s load_gen=%d", title or "<unknown>", d.load_gen)
        LOG.stats.record_transition(deck, "track_loaded")

        if self._resolver is None:
            return

        # Prefer ANLZ-based resolution (no subprocess, fires before this event)
        anlz_path = self._pending_anlz_path.pop(deck, None)
        if anlz_path:
            log.debug("track load: deck %d using ANLZ path for resolution", deck)
            self._resolver.resolve_by_anlz(deck, d.load_gen, anlz_path, trace_id=trace_id)
        else:
            other = 3 - deck
            other_path = self._deck[other].meta.filepath
            # Fire both: lsof (fast, uses track length) and title-based DB lookup
            # (reliable fallback when memory track_length=0 prevents lsof from matching)
            self._resolver.resolve_async(deck, d.load_gen, other_path, trace_id=trace_id)
            if title:
                self._resolver.resolve_by_title(deck, d.load_gen, title, trace_id=trace_id)

    def attach_resolver(self, resolver) -> None:  # type: ignore[type-arg]
        self._resolver = resolver

    # ── Filepath resolved ─────────────────────────────────────────────────────

    def _on_filepath_resolved(self, deck: int, payload: dict) -> None:
        d = self._deck[deck]
        gen = payload.get("load_gen", -1)
        if gen != d.load_gen:
            log.debug("FILEPATH_RESOLVED stale result gen=%d current=%d - discarding",
                      gen, d.load_gen)
            return

        meta = d.meta
        meta.filepath       = payload["filepath"]
        meta.bpm            = payload["bpm"]
        meta.content_id     = payload["content_id"]
        meta.first_beat_ms  = payload["first_beat_ms"]
        meta.beatgrid_times_ms = list(payload.get("beatgrid_times_ms", []))
        meta.beatgrid_bpms = list(payload.get("beatgrid_bpms", []))
        meta.beatgrid_source = payload.get("beatgrid_source", "")
        meta.soundswitch_id = payload["soundswitch_id"]
        meta.total_ms       = payload["total_ms"]
        if self._live_bpm is not None and meta.bpm > 0:
            try:
                self._live_bpm.update_hint(deck, meta.bpm, meta.bpm)
            except Exception:
                log.debug("live BPM library hint update failed", exc_info=True)

        load_delta_ms = 0.0
        if deck in self._load_mono:
            load_delta_ms = (time.monotonic() - self._load_mono[deck]) * 1000.0
        log.info("FILEPATH_RESOLVED path=%s bpm=%.1f ssid=%s latency=%.1fms",
                 payload["filepath"].split("/")[-1], meta.bpm,
                 "yes" if meta.soundswitch_id else "no", load_delta_ms)
        if _os.environ.get("RBSS_RB_STATE_SHADOW") == "1":  # A6 shadow log
            ssid = meta.soundswitch_id
            if ssid:
                scripted_id = next(
                    (tid for tid, t in SCRIPTED_TRACKS.items() if t.get("ssid") == ssid),
                    None,
                )
                log.info("[SCRIPTED][DIRECT] deck=%d scripted_id=%s ssid=%.8s latency_ms=%.1f",
                         deck, scripted_id if scripted_id is not None else "none",
                         ssid, load_delta_ms)
            else:
                log.info("[SCRIPTED][DIRECT] deck=%d scripted=no ssid=none latency_ms=%.1f",
                         deck, load_delta_ms)
        LOG.stats.record_transition(deck, "filepath_resolved")
        if _os.environ.get("RBSS_SCRIPTED_DIRECT") == "1":
            ssid = meta.soundswitch_id
            filepath = meta.filepath
            scripted_id = None
            matched_by_filepath = False
            if ssid:
                scripted_id = next(
                    (tid for tid, t in SCRIPTED_TRACKS.items() if t.get("ssid") == ssid),
                    None,
                )
            if scripted_id is None and filepath:
                filepath_matches = [
                    tid for tid, t in SCRIPTED_TRACKS.items()
                    if t.get("filepath") == filepath
                ]
                if len(filepath_matches) == 1:
                    scripted_id = filepath_matches[0]
                    matched_by_filepath = True
                elif len(filepath_matches) > 1:
                    log.info(
                        "[SCRIPTED][DIRECT] deck=%d scripted=no filepath=%s "
                        "ambiguous_matches=%d latency_ms=%.1f",
                        deck,
                        _os.path.basename(filepath),
                        len(filepath_matches),
                        load_delta_ms,
                    )
            if scripted_id is not None:
                log_fn = log.warning if matched_by_filepath and not ssid else log.info
                log_fn("[SCRIPTED][DIRECT] deck=%d scripted_id=%d ssid=%.8s latency_ms=%.1f",
                       deck, scripted_id, ssid, load_delta_ms)
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.SCRIPTED_ARM,
                        deck=deck,
                        payload={"scripted_id": scripted_id},
                        source="filepath_resolved",
                    ))
                except queue.Full:
                    log.warning("[SCRIPTED][DIRECT] queue full; SCRIPTED_ARM dropped deck=%d",
                                deck)
            else:
                if ssid:
                    log.info(
                        "[SCRIPTED][DIRECT] deck=%d scripted=no ssid=%.8s filepath=%s "
                        "latency_ms=%.1f",
                        deck,
                        ssid,
                        _os.path.basename(filepath) if filepath else "none",
                        load_delta_ms,
                    )
                else:
                    log.info("[SCRIPTED][DIRECT] deck=%d scripted=no ssid=none latency_ms=%.1f",
                             deck, load_delta_ms)
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.SCRIPTED_CLEAR,
                        deck=deck,
                        source="filepath_resolved",
                    ))
                except queue.Full:
                    log.warning("[SCRIPTED][DIRECT] queue full; SCRIPTED_CLEAR dropped deck=%d",
                                deck)

    # ── Scripted arm / clear ──────────────────────────────────────────────────

    def _arm_scripted(self, deck: int, track_id: int) -> None:
        # FM-1: non-blocking two-phase arm — no time.sleep() in push loop thread
        track = st_lookup(track_id)
        if not track:
            log.warning("SCRIPTED_ARM failed unknown_id=%d", track_id)
            return

        # Debounce concurrent arm calls
        key = (track_id, deck)
        now = time.monotonic()
        if now - self._arm_times.get(key, 0.0) < 2.0:
            log.debug("[SS] arm scripted debounced: id=%d deck=%d", track_id, deck)
            return
        self._arm_times[key] = now
        self._os.last_arm_mono = now

        # Apply track data to DeckState
        d = self._deck[deck]
        d.scripted_id        = track_id
        d.meta.filepath      = track["filepath"]
        d.meta.bpm           = track["bpm"]
        d.meta.first_beat_ms = track["first_beat_ms"]
        d.meta.beatgrid_times_ms = []
        d.meta.beatgrid_bpms = []
        d.meta.beatgrid_source = ""
        d.meta.total_ms      = float(track.get("total_ms", 0))
        # FM-5: use ssid from registry (populated at startup by resolve_filepaths)
        # never do synchronous disk I/O here
        if not d.meta.soundswitch_id:
            d.meta.soundswitch_id = track.get("ssid", "")

        # Get current elapsed — prefer memory snap, fall back to d.elapsed_ms which
        # the push loop keeps current via TL TC when the DPU is unresolvable (DVS mode).
        snap = self._cache.get(deck)
        if snap and not snap.is_stale():
            elapsed_ms = snap.elapsed_ms
        else:
            elapsed_ms = self._deck[deck].elapsed_ms  # maintained by push loop
        elapsed_ms += TIMING_COMPENSATION_MS

        mirror = 3 - deck

        log.info("SCRIPTED_ARM id=%d path=%s elapsed=%dms bpm=%.1f first_beat=%.1fms",
                 track_id, track["filepath"].split("/")[-1] if track["filepath"] else "?",
                 elapsed_ms, d.meta.bpm, d.meta.first_beat_ms)
        LOG.stats.record_transition(deck, "scripted_arm")

        # Phase 0 (immediate): clear all 4 SS deck slots, stop playback + any autoloop
        for dk in (deck, mirror, 3, 4):
            self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            self._out.send_loop_off(dk)
            self._out.send_deck_play(dk, "off")

        # Phase 1 (scheduled): send_deck_load after SS has processed the clear
        arm_meta = TrackMetadata(
            filepath=d.meta.filepath, soundswitch_id=d.meta.soundswitch_id,
            bpm=d.meta.bpm, first_beat_ms=d.meta.first_beat_ms, total_ms=d.meta.total_ms,
            beatgrid_times_ms=list(d.meta.beatgrid_times_ms),
            beatgrid_bpms=list(d.meta.beatgrid_bpms),
            beatgrid_source=d.meta.beatgrid_source,
        )
        object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)

        self._pending_arm = ArmSequence(
            deck=deck,
            track_id=track_id,
            fire_at=now + 0.10,
            arm_meta=arm_meta,
            elapsed_ms=elapsed_ms,
            mirror=mirror,
            active_deck=self._os.active_deck,
        )

    def _check_pending_arm(self) -> None:
        """FM-1: fire phase 1 of a pending scripted arm (send_deck_load) when timer expires."""
        arm = self._pending_arm
        if arm is None or time.monotonic() < arm.fire_at:
            return
        self._pending_arm = None
        log.info("[SS] arm scripted phase2: id=%d  deck=%d", arm.track_id, arm.deck)
        # Refresh elapsed in case position advanced since phase 0
        snap = self._cache.get(arm.deck)
        elapsed_ms = (snap.elapsed_ms if snap and not snap.is_stale() else arm.elapsed_ms) + TIMING_COMPENSATION_MS
        arm_meta = arm.arm_meta
        object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)
        # Use current active_deck, not the snapshot — deck may have switched in 100ms
        cur_active = self._os.active_deck
        # Send to all 4 SS deck slots: active + mirror bridge deck + VDJ layers 3/4.
        # Phase 0 clears all 4; if mirror is not reloaded here the push loop sends
        # elapsed to an empty SS deck, which confuses SS's scripted show engine.
        # Matches v1 behaviour: always load both bridge decks at arm time.
        for dk in (arm.deck, arm.mirror, 3, 4):
            self._out.send_deck_load(dk, arm_meta, cur_active, play="on")
        self._log_status()

    def _arm_unscripted(self, deck: int) -> None:
        """TL value=1: clear scripted state. Lighting machine re-evaluates next tick."""
        d = self._deck[deck]
        log.info("[D%d] scripted cleared", deck)
        d.scripted_id = 0
        d.meta.soundswitch_id = ""

    # ── Lighting state machine ────────────────────────────────────────────────

    def _update_lighting(
        self,
        deck: int,
        d: "DeckState",
        is_playing: bool,
        elapsed_ms: int,
        bpm: float,
        now: float,
    ) -> None:
        """Derive and apply lighting mode from master deck state. Called every tick.

        Rule:
          scripted track + playing  → SCRIPTED_MODE
          unscripted track + playing → AUTOLOOP_MODE
          not playing               → IDLE (debounced by STOP_DEBOUNCE_S)

        Only fires SS output on mode transitions. Fully state-derived — not
        event-driven, so missed events cannot leave SS in a stale mode.
        """
        os = self._os

        if d.scripted_id and is_playing:
            desired = "scripted"
        elif is_playing:
            desired = "autoloop"
        else:
            desired = "idle"

        # Track when desired last changed so we can debounce idle transitions.
        if desired != os.lighting_desired:
            os.lighting_desired = desired
            os.lighting_stable_since = now

        # Idle transitions are debounced to prevent flicker on transient pauses.
        debounce_s = STOP_DEBOUNCE_S if desired == "idle" else 0.0
        if desired == "idle" and os.lighting_mode == "autoloop":
            debounce_s = _AUTOLOOP_IDLE_DEBOUNCE_S
        if (now - os.lighting_stable_since) < debounce_s:
            return

        if desired == os.lighting_mode:
            # No mode change, but re-arm autoloop if filepath arrived after the initial arm.
            if desired == "autoloop" and d.meta.filepath and d.meta.filepath != os.last_armed_filepath:
                log.info("[SS] autoloop re-arm: %s", d.meta.filepath.split("/")[-1])
                self._apply_lighting(deck, "autoloop", elapsed_ms, bpm)
            return

        log.info("[SS] %s → %s  deck=%d  elapsed=%dms",
                 os.lighting_mode, desired, deck, elapsed_ms)
        os.lighting_mode = desired
        self._apply_lighting(deck, desired, elapsed_ms, bpm)

    def _apply_lighting(self, deck: int, mode: str, elapsed_ms: int, bpm: float) -> None:
        """Send SS commands for a lighting mode transition. No blocking, no sleep.

        Called only by _update_lighting, only on actual mode changes.
        """
        mirror = 3 - deck
        d = self._deck[deck]
        self._os.last_arm_mono = time.monotonic()

        if mode == "scripted":
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            # Arm the scripted show. _arm_scripted is internally debounced (2 s)
            # so rapid pause/resume doesn't cause a full re-arm sequence.
            self._arm_scripted(deck, d.scripted_id)

        elif mode == "autoloop":
            self._pending_arm = None
            self._os.push_reset_bpm = True
            arm_bpm, bpm_source = self._autoloop_arm_bpm(deck, d.meta.bpm)
            self._os.autoloop_arm_bpm = arm_bpm
            self._os.autoloop_arm_deck = deck
            self._os.autoloop_arm_pending = True
            self._os.autoloop_arm_sync_beat = 0
            self._os.autoloop_arm_pending_since = time.monotonic()
            self._os.last_autoloop_status_phrase_beat = 0
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_autoloop_tempo_anchor()
            self._clear_pending_autoloop_master_phrase_arm()
            self._os.last_live_follow_bpm = arm_bpm
            self._os.last_live_follow_send_mono = 0.0
            self._os.live_follow_generation += 1
            arm_after_master = self._os.autoloop_arm_after_master_change
            arm_source = self._os.autoloop_master_change_source
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            log.info("[SS][AUTOLOOP-ARM] deck=%d mirror=%d elapsed=%dms loop=%d "
                     "source=%s timing_bpm=%.2f arm_bpm=%.2f meta_bpm=%.2f "
                     "after_master=%s master_source=%s "
                     "file=%s previous=%s",
                     deck, mirror, elapsed_ms, AUTOLOOP_BEATS,
                     bpm_source, arm_bpm, arm_bpm, d.meta.bpm,
                     arm_after_master, arm_source or "<none>",
                     d.meta.filepath.split("/")[-1] if d.meta.filepath else "<none>",
                     self._os.last_armed_filepath.split("/")[-1]
                     if self._os.last_armed_filepath else "<none>")
            if arm_after_master and self._autoloop_master_phrase_arm:
                for dk in (deck, mirror, 3, 4):
                    self._out.send_deck_clear(dk)
                    self._out.send_loop_off(dk)
                log.info("[SS][AUTOLOOP-MASTER-CLEAR] deck=%d mirror=%d source=%s",
                         deck, mirror, arm_source or "<none>")
            else:
                for dk in (deck, mirror, 3, 4):
                    self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            if d.meta.filepath:
                self._os.last_armed_filepath = d.meta.filepath
                arm_meta = TrackMetadata(
                    filepath=d.meta.filepath,
                    soundswitch_id="",
                    bpm=arm_bpm,
                    first_beat_ms=d.meta.first_beat_ms,
                    beatgrid_times_ms=list(d.meta.beatgrid_times_ms),
                    beatgrid_bpms=list(d.meta.beatgrid_bpms),
                    beatgrid_source=d.meta.beatgrid_source,
                    total_ms=d.meta.total_ms,
                )
                object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)
                abs_beat = self._autoloop_abs_beat_for_elapsed(elapsed_ms, arm_bpm, arm_meta)
                self._set_autoloop_tempo_anchor(elapsed_ms, abs_beat, arm_bpm)
                if self._should_delay_autoloop_master_arm(arm_after_master, abs_beat):
                    target = self._next_autoloop_arm_phrase(abs_beat)
                    target_elapsed_ms, target_source = self._autoloop_target_elapsed_for_beat(
                        target, elapsed_ms, arm_bpm, arm_meta,
                    )
                    pending_reason = "scheduled"
                    if target_elapsed_ms - elapsed_ms < _AUTOLOOP_PHRASE_MIN_RUNWAY_MS:
                        pending_reason = "short-runway"
                    self._os.autoloop_arm_sync_beat = target
                    self._os.autoloop_arm_target_elapsed_ms = target_elapsed_ms
                    self._os.autoloop_arm_target_source = target_source
                    self._os.pending_autoloop_arm_meta = arm_meta
                    self._os.pending_autoloop_arm_deck = deck
                    self._os.pending_autoloop_arm_mirror = mirror
                    self._os.pending_autoloop_arm_active = deck
                    self._os.pending_autoloop_arm_source = arm_source or "master"
                    self._os.pending_autoloop_arm_reason = pending_reason
                    log.info("[SS][AUTOLOOP-MASTER-ARM-PENDING] deck=%d mirror=%d "
                             "current_beat=%.1f current_elapsed_ms=%d "
                             "target_beat=%d target_elapsed_ms=%d until_ms=%d "
                             "grid_source=%s file=%s source=%s reason=%s",
                             deck, mirror, abs_beat, elapsed_ms,
                             target, target_elapsed_ms,
                             target_elapsed_ms - elapsed_ms, target_source,
                             d.meta.filepath.split("/")[-1], arm_source or "<none>",
                             pending_reason)
                else:
                    self._send_autoloop_deck_load(deck, mirror, deck, arm_meta)
                    if arm_after_master and self._autoloop_master_phrase_arm:
                        phrase_beat = self._previous_autoloop_arm_phrase(abs_beat)
                        phrase_elapsed_ms, phrase_source = self._autoloop_target_elapsed_for_beat(
                            phrase_beat, elapsed_ms, arm_bpm, arm_meta,
                        )
                        lateness_ms = max(0, elapsed_ms - phrase_elapsed_ms)
                        if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
                            self._schedule_autoloop_master_correction(
                                deck, mirror, deck, arm_meta, arm_bpm, elapsed_ms,
                                phrase_beat, arm_source or "master", "phrase-grace-late",
                            )
                            log.warning("[SS][AUTOLOOP-MASTER-ARM-GRACE-LATE] deck=%d "
                                        "phrase_beat=%d phrase_elapsed_ms=%d "
                                        "current_elapsed_ms=%d lateness_ms=%d "
                                        "tolerance_ms=%d grid_source=%s",
                                        deck, phrase_beat, phrase_elapsed_ms,
                                        elapsed_ms, lateness_ms,
                                        _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS,
                                        phrase_source)
            else:
                self._os.last_armed_filepath = ""
                for dk in (deck, mirror):
                    self._deck[dk].meta.first_beat_ms = 0.0
                abs_beat = self._autoloop_abs_beat_for_elapsed(elapsed_ms, arm_bpm, d.meta)
                self._set_autoloop_tempo_anchor(elapsed_ms, abs_beat, arm_bpm)
                for dk in (deck, mirror, 3, 4):
                    self._out.send_loop_on(dk)
                    self._out._sub(f"deck {dk} play", "on", verbose=True)
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""

        elif mode == "idle":
            self._pending_arm = None
            self._os.last_armed_filepath = ""
            self._os.autoloop_arm_bpm = 0.0
            self._os.autoloop_arm_deck = 0
            self._os.last_autoloop_status_phrase_beat = 0
            self._os.autoloop_arm_after_master_change = False
            self._os.autoloop_master_change_source = ""
            self._clear_autoloop_arm_phrase_lock()
            self._clear_live_bpm_follow()
            self._clear_autoloop_tempo_relock()
            self._clear_autoloop_tempo_anchor()
            self._clear_pending_autoloop_master_phrase_arm()
            self._os.live_follow_generation += 1
            for dn in range(1, 5):
                self._out.send_deck_play(dn, "off")
                self._out._sub(f"deck {dn} loop", "off", verbose=True)
            for dn in range(1, 5):
                self._out.send_deck_clear(dn)

    # ── Push loop ─────────────────────────────────────────────────────────────

    def _push_tick(self) -> None:
        # FM-1: check two-phase arm timer before any other push logic
        self._check_pending_arm()

        now = time.monotonic()
        os  = self._os
        active = os.active_deck
        d   = self._deck[active]
        mirror = 3 - active

        # ── Read position from memory ─────────────────────────────────────────
        snap = self._cache.get(active)

        # When memory has no snap for this deck (DPU unresolved — e.g. no track
        # loaded in RB, DVS mode, or DPU2 vtable mismatch), synthesize a snap
        # from TL TC so the push loop can resume/beat/elapsed normally.
        # TL TC fires every ~15 s from ENGINE STATE; 45 s guard limits drift.
        if snap is None:
            tl_ms, tl_at, tl_pitch = self._tl_tc.get(active, (0, 0.0, 1.0))
            if tl_ms > 0 and tl_at > 0 and (now - tl_at) < 45.0:
                age_ms = (now - tl_at) * 1000.0 * tl_pitch
                snap = PositionSnapshot(
                    deck=active,
                    elapsed_ms=int(tl_ms + (age_ms if d.playing else 0.0)),
                    playing=d.playing,
                    track_length_ms=0,
                    updated_at=now,
                )

        # FM-11: if memory is stale (RB gone / unreadable), force stop if playing.
        # If not playing: still run lighting machine + auto-detect so deck switches
        # and arm transitions are not blocked by a temporarily unreadable DPU.
        if snap is None or snap.is_stale(MEM_STALE_S):
            if os.was_playing:
                log.warning("[D%d] memory stale — forcing stop", active)
                self._pending_arm = None
                self._do_stop(active, os.last_beat_elapsed_ms)
                return
            # Not playing — run lighting machine and auto-detect with TL state only.
            bpm = d.meta.bpm
            elapsed_ms = d.elapsed_ms or 0
            confident_playing = d.playing
            self._update_lighting(active, d, confident_playing, elapsed_ms, bpm, now)
            arm_guard = (now - os.last_arm_mono) < ARM_GUARD_S
            if not d.playing and not arm_guard:
                if self._deck[mirror].playing:
                    log.info("[D%d→D%d] auto-switch (D%d idle, D%d playing)",
                             active, mirror, active, mirror)
                    os.last_arm_mono = now
                    try:
                        self._eq.put_nowait(BridgeEvent(
                            kind=Ev.MASTER_CHANGED, deck=mirror, source="auto-detect",
                        ))
                    except queue.Full:
                        log.warning("[D%d→D%d] auto-switch dropped: queue full",
                                    active, mirror)
            return

        # Interpolate position: memory updates at 60 Hz; push loop at 200 Hz
        elapsed_since = (now - snap.updated_at) * 1000.0
        raw_elapsed_ms = snap.elapsed_ms + (elapsed_since if snap.playing else 0.0)
        mem_playing = snap.playing

        # TL TC fallback: when memory gives 0 (v2's container/DPU path reaches the wrong
        # inner for deck 2 in DDJ-800 mode — the correct deck-2 inner does write position
        # at +0xC, but it's reachable via outer+0x78, not container+0x480 or DPU scan).
        if snap.elapsed_ms == 0:
            tl_ms, tl_at, tl_pitch = self._tl_tc.get(active, (0, 0.0, 1.0))
            if tl_ms > 0 and tl_at > 0 and (now - tl_at) < 45.0:
                age_ms = (now - tl_at) * 1000.0 * tl_pitch
                raw_elapsed_ms = tl_ms + (age_ms if (mem_playing or d.playing) else 0.0)

        elapsed_ms = int(raw_elapsed_ms) + TIMING_COMPENSATION_MS
        d.elapsed_ms = elapsed_ms

        # ── Rate-limited timecode log (once per 5 s, both decks) ────────────────
        if now - self._last_pos_log[active] >= 5.0:
            self._last_pos_log[active] = now
            tm, ts = divmod(elapsed_ms // 1000, 60)
            tms    = elapsed_ms % 1000
            log.info("[D%d] %d:%02d.%03d  bpm=%.1f  %s%s",
                     active, tm, ts, tms, d.meta.bpm,
                     d.meta.filepath.split("/")[-1] if d.meta.filepath else "<no track>",
                     "  scripted" if d.scripted_id else "")

        mirror_snap = self._cache.get(mirror)
        if mirror_snap and now - self._last_pos_log[mirror] >= 5.0:
            self._last_pos_log[mirror] = now
            dm = self._deck[mirror]
            me = mirror_snap.elapsed_ms
            mm, ms2 = divmod(me // 1000, 60)
            mms    = me % 1000
            log.info("[D%d] %d:%02d.%03d  bpm=%.1f  %s%s",
                     mirror, mm, ms2, mms, dm.meta.bpm,
                     dm.meta.filepath.split("/")[-1] if dm.meta.filepath else "<no track>",
                     "  scripted" if dm.scripted_id else "")

        # ── BPM and beat position ─────────────────────────────────────────────
        bpm = d.meta.bpm
        if os.lighting_mode == "autoloop" and os.autoloop_arm_deck == active and os.autoloop_arm_bpm > 0:
            bpm = os.autoloop_arm_bpm
        if os.push_reset_bpm:
            os.last_sent_bpm = 0.0
            os.push_reset_bpm = False

        # Beat position: computed from ENGINE STATE BPM (pitch-adjusted every ~15s).
        beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms) if bpm > 0 else 0.0
        beat_ms = 60_000.0 / bpm if bpm > 0 else 0.0
        abs_beat_pos = (
            self._autoloop_fallback_abs_beat_for_elapsed(active, elapsed_ms, bpm, d.meta.first_beat_ms)
            if beat_ms > 0 else 0.0
        )
        grid_pos = None
        if os.lighting_mode == "autoloop":
            grid_pos = _compute_beatgrid_position(elapsed_ms, d.meta.beatgrid_times_ms)
            if grid_pos is not None:
                beat_pos, abs_beat_pos = grid_pos
        bpm = self._maybe_apply_live_bpm_follow(active, mirror, bpm, abs_beat_pos, now)
        if bpm > 0 and grid_pos is None:
            beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms)
            beat_ms = 60_000.0 / bpm
            abs_beat_pos = self._autoloop_fallback_abs_beat_for_elapsed(
                active, elapsed_ms, bpm, d.meta.first_beat_ms,
            )

        # ── Stop detection ────────────────────────────────────────────────────
        # TL PAUSE event sets d.playing=False; memory confirms it persists.
        # In v2 (no Frida), TL log is the authoritative play source.
        # is_playing (OR) is kept for other_playing / auto-detect where memory
        # corroboration helps guard against mis-mapped DPU offsets.
        is_playing = mem_playing or d.playing

        # ── Lighting state machine ────────────────────────────────────────────
        # TL is authoritative: d.playing=False (TL said pause) means not playing,
        # even if memory (unreliable on DDJ-800 mode=4112) still shows playing.
        confident_playing = d.playing
        self._update_lighting(active, d, confident_playing, elapsed_ms, bpm, now)
        if os.lighting_mode == "autoloop" and grid_pos is None:
            grid_pos = _compute_beatgrid_position(elapsed_ms, d.meta.beatgrid_times_ms)
            if grid_pos is not None:
                beat_pos, abs_beat_pos = grid_pos

        # Arm guard recomputed here so it reflects any arm fired by _update_lighting.
        arm_guard = (now - os.last_arm_mono) < ARM_GUARD_S

        # Stop detection is TL-authoritative for the same reason: d.playing=False
        # means stopped, memory cannot override a TL pause event.
        if not d.playing and not arm_guard and os.was_playing:
            if os.not_playing_since == 0.0:
                os.not_playing_since = now
            stop_confirmed = (now - os.not_playing_since) >= STOP_DEBOUNCE_S
        else:
            if d.playing:
                os.not_playing_since = 0.0
            stop_confirmed = False

        # Check other deck for auto-switch.
        # Require TL confirmation (d.playing) in addition to memory — guards against
        # wrong DPU offsets causing memory to misreport the other deck as playing.
        other_snap = self._cache.get(mirror)
        other_playing = ((other_snap is not None and not other_snap.is_stale()
                          and other_snap.playing)
                         and self._deck[mirror].playing)

        if stop_confirmed and os.was_playing:
            if other_playing and not arm_guard:
                log.info("[D%d→D%d] auto-switch (D%d stopped)", active, mirror, active)
                os.not_playing_since = 0.0
                os.last_arm_mono = now
                # FM-2: post to queue so _on_master_changed runs in event-loop thread
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.MASTER_CHANGED,
                        deck=mirror,
                        source="pause auto-switch",
                    ))
                except queue.Full:
                    log.warning("[D%d→D%d] auto-switch dropped: event queue full", active, mirror)
            else:
                self._do_stop(active, elapsed_ms)
            return

        # ── Auto-detect: active idle + mirror playing → switch ───────────────
        # Handles the case where TL doesn't send MASTER_CHANGED (e.g. track loaded
        # on deck 2 with nothing on deck 1 — RB may auto-assign master without a
        # deck-change log line).
        if not os.was_playing and not d.playing and not arm_guard:
            if self._deck[mirror].playing:
                log.info("[D%d→D%d] auto-switch (D%d idle, D%d playing)", active, mirror, active, mirror)
                os.last_arm_mono = now
                try:
                    self._eq.put_nowait(BridgeEvent(
                        kind=Ev.MASTER_CHANGED, deck=mirror, source="auto-detect",
                    ))
                except queue.Full:
                    log.warning("[D%d→D%d] auto-switch dropped: event queue full", active, mirror)

        # ── Resume detection (was stopped, now playing) ───────────────────────
        # TL authoritative: d.playing=True means TL confirmed playback.
        real_play = d.playing
        if not os.was_playing and real_play:
            if os.play_settle_after == 0.0:
                os.play_settle_after = now + PLAY_SETTLE_MS / 1000.0
                log.info("[D%d] resuming — settle window %.0f ms", active, PLAY_SETTLE_MS)
            elif now >= os.play_settle_after:
                os.play_settle_after = 0.0
                self._do_resume(active, elapsed_ms, bpm)
            return   # don't emit beats until flash-arm fires

        if not os.was_playing:
            return

        # ── Emit elapsed + beat ───────────────────────────────────────────────
        if os.lighting_mode == "autoloop" and os.autoloop_arm_pending:
            self._maybe_lock_autoloop_arm(active, mirror, bpm, abs_beat_pos, elapsed_ms)

        # BPM: send immediately when last_sent_bpm is 0 (fresh arm / deck switch) so
        # SS autoloop activates on the current tick, not at the next beat boundary.
        # VDJ sends BPM to all 4 decks; SS may use deck 3/4 internally.
        if bpm > 0 and os.last_sent_bpm == 0.0:
            for dk in (active, mirror, 3, 4):
                self._out.send_bpm(dk, bpm)
            os.last_sent_bpm = bpm
        elif bpm > 0 and os.last_sent_bpm > 0:
            threshold = (BPM_THRESHOLD_SCRIPTED if d.scripted_id
                         else BPM_THRESHOLD_UNSCRIPTED)
            if abs(bpm - os.last_sent_bpm) > threshold:
                for dk in (active, mirror, 3, 4):
                    self._out.send_bpm(dk, bpm)
                os.last_sent_bpm = bpm

        # Beat boundary detection: fire a beat event when elapsed crosses the next beat
        beatpos_out = abs_beat_pos if os.lighting_mode == "autoloop" else beat_pos
        if bpm > 0:
            this_beat = int(abs_beat_pos)
            if os.lighting_mode == "autoloop" and grid_pos is not None:
                last_grid_pos = _compute_beatgrid_position(
                    os.last_beat_elapsed_ms, d.meta.beatgrid_times_ms,
                )
                last_beat = int(last_grid_pos[1]) if last_grid_pos is not None else this_beat
            elif os.lighting_mode == "autoloop":
                last_abs_beat = self._autoloop_fallback_abs_beat_for_elapsed(
                    active, os.last_beat_elapsed_ms, bpm, d.meta.first_beat_ms,
                )
                last_beat = int(last_abs_beat)
            else:
                last_beat = int((os.last_beat_elapsed_ms - d.meta.first_beat_ms) / beat_ms) if beat_ms > 0 else 0

            if this_beat > last_beat:
                beat_index = this_beat % 4
                if os.pending_autoloop_arm_meta is not None:
                    self._maybe_lock_autoloop_arm(active, mirror, bpm, abs_beat_pos, elapsed_ms)
                if os.lighting_mode == "autoloop":
                    beat_out = this_beat
                    pending_live_bpm = os.pending_live_bpm
                    if pending_live_bpm > 0:
                        for dk in (active, mirror, 3, 4):
                            self._out.send_bpm(dk, pending_live_bpm)
                        bpm = pending_live_bpm
                        os.autoloop_arm_bpm = pending_live_bpm
                        self._set_autoloop_tempo_anchor(elapsed_ms, abs_beat_pos, pending_live_bpm)
                        os.last_live_follow_bpm = pending_live_bpm
                        os.last_live_follow_send_mono = now
                        os.last_sent_bpm = pending_live_bpm
                        os.pending_live_bpm = 0.0
                        change = True
                        log.info("[SS][LIVE-BPM-APPLY] deck=%d bpm=%.2f beat=%d",
                                 active, pending_live_bpm, this_beat)
                    else:
                        change = os.autoloop_change_on_next_beat
                    os.autoloop_change_on_next_beat = False
                else:
                    beat_out = beat_index
                    change = (beat_index == 0)
                os.last_beat_elapsed_ms = elapsed_ms
                for dk in (active, mirror, 3, 4):
                    self._out.send_beat(dk, bpm, beat_out, change=change)
                self._maybe_lock_autoloop_arm(active, mirror, bpm, abs_beat_pos, elapsed_ms)
                if os.lighting_mode == "autoloop":
                    phrase_beat = (this_beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS
                    if (
                        phrase_beat > 0
                        and phrase_beat > last_beat
                        and phrase_beat != os.last_autoloop_status_phrase_beat
                    ):
                        os.last_autoloop_status_phrase_beat = phrase_beat
                        grid_status = d.meta.beatgrid_source if grid_pos is not None else "fallback"
                        self._log_autoloop_tick(
                            active, elapsed_ms, beatpos_out, bpm, d.meta.bpm, grid_status
                        )

        # Elapsed + beatpos — send at every push tick (SS needs continuous updates).
        # Test A: in autoloop only, send absolute beat position to match VDJ-like
        # OS2L timing while leaving beat events unchanged for isolation.
        for dk in (active, mirror, 3, 4):
            self._out.send_elapsed(dk, elapsed_ms, beatpos_out)

    # ── Stop / resume helpers ─────────────────────────────────────────────────

    def _do_stop(self, deck: int, elapsed_ms: int) -> None:
        log.info("[D%d] stopped", deck)
        os = self._os
        self._deck[deck].playing  = False
        os.was_playing            = False
        os.last_beat_elapsed_ms   = elapsed_ms
        os.stop_elapsed_ms        = elapsed_ms
        os.not_playing_since      = 0.0
        os.last_sent_bpm          = 0.0
        os.autoloop_arm_bpm       = 0.0
        os.autoloop_arm_deck      = 0
        os.last_autoloop_status_phrase_beat = 0
        self._clear_autoloop_arm_phrase_lock()
        self._clear_live_bpm_follow()
        self._clear_autoloop_tempo_relock()
        self._clear_autoloop_tempo_anchor()
        os.live_follow_generation += 1

    def _do_resume(self, deck: int, elapsed_ms: int, bpm: float) -> None:
        mirror = 3 - deck
        d = self._deck[deck]
        m = self._deck[mirror]
        log.info("[D%d] resume  elapsed=%dms  bpm=%.1f  %s",
                 deck, elapsed_ms, bpm, d.meta.filepath.split("/")[-1] if d.meta.filepath else "<no track>")

        # Deck mismatch correction: if active deck is empty but other has track, swap
        if not d.meta.filepath and m.meta.filepath:
            log.info("[D%d→D%d] correcting: active deck empty, D%d has track", deck, mirror, mirror)
            self._os.active_deck = mirror
            deck, mirror = mirror, deck
            d, m = m, d

        self._os.was_playing          = True
        self._os.last_sent_bpm        = 0.0
        self._os.last_beat_elapsed_ms = elapsed_ms
        self._os.last_autoloop_status_phrase_beat = 0
        self._log_status()

    def _log_autoloop_tick(
        self,
        active: int,
        elapsed_ms: int,
        beatpos_out: float,
        timing_bpm: float,
        meta_bpm: float,
        grid_status: str,
    ) -> None:
        os = self._os
        live_status = self._live_bpm_status_text(active)
        log.info("[SS][AUTOLOOP-TICK] deck=%d elapsed=%dms beat=%.2f "
                 "timing_bpm=%.2f arm_bpm=%.2f meta_bpm=%.2f grid=%s %s %s file=%s",
                 active, elapsed_ms, beatpos_out,
                 timing_bpm, os.autoloop_arm_bpm, meta_bpm, grid_status, live_status,
                 self._live_bpm_follow_status_text(),
                 os.last_armed_filepath.split("/")[-1]
                 if os.last_armed_filepath else "<none>")

    def _should_delay_autoloop_master_arm(self, arm_after_master: bool, abs_beat_pos: float) -> bool:
        if not self._autoloop_master_phrase_arm or not arm_after_master:
            return False
        return not self._is_near_autoloop_phrase_start(abs_beat_pos)

    def _is_near_autoloop_phrase_start(self, abs_beat_pos: float) -> bool:
        phrase_offset = math.fmod(max(abs_beat_pos, 0.0), AUTOLOOP_ARM_PHRASE_BEATS)
        if phrase_offset < 0:
            phrase_offset += AUTOLOOP_ARM_PHRASE_BEATS
        return phrase_offset <= _AUTOLOOP_MASTER_PHRASE_START_GRACE_BEATS

    def _autoloop_abs_beat_for_elapsed(
        self,
        elapsed_ms: int,
        bpm: float,
        meta: TrackMetadata,
    ) -> float:
        grid_pos = _compute_beatgrid_position(elapsed_ms, meta.beatgrid_times_ms)
        if grid_pos is not None:
            return grid_pos[1]
        if bpm <= 0:
            return 0.0
        beat_ms = 60_000.0 / bpm
        return (elapsed_ms - meta.first_beat_ms) / beat_ms

    def _autoloop_target_elapsed_for_beat(
        self,
        target_beat: int,
        current_elapsed_ms: int,
        bpm: float,
        meta: TrackMetadata,
    ) -> tuple[int, str]:
        grid_target = _beatgrid_elapsed_for_abs_beat(target_beat, meta.beatgrid_times_ms)
        if grid_target is not None:
            return grid_target
        if bpm <= 0:
            return current_elapsed_ms, "fallback"
        beat_ms = 60_000.0 / bpm
        os = self._os
        if os.autoloop_anchor_bpm > 0:
            elapsed_ms = os.autoloop_anchor_elapsed_ms + (
                (target_beat - os.autoloop_anchor_abs_beat) * beat_ms
            )
        else:
            elapsed_ms = meta.first_beat_ms + (target_beat * beat_ms)
        return int(round(elapsed_ms)), "fallback"

    def _autoloop_fallback_abs_beat_for_elapsed(
        self,
        deck: int,
        elapsed_ms: int,
        bpm: float,
        first_beat_ms: float,
    ) -> float:
        os = self._os
        if (
            os.lighting_mode == "autoloop"
            and os.autoloop_arm_deck == deck
            and os.autoloop_anchor_bpm > 0
            and bpm > 0
        ):
            beat_ms = 60_000.0 / bpm
            return os.autoloop_anchor_abs_beat + (
                (elapsed_ms - os.autoloop_anchor_elapsed_ms) / beat_ms
            )
        if bpm <= 0:
            return 0.0
        beat_ms = 60_000.0 / bpm
        return (elapsed_ms - first_beat_ms) / beat_ms

    def _set_autoloop_tempo_anchor(self, elapsed_ms: int, abs_beat: float, bpm: float) -> None:
        os = self._os
        os.autoloop_anchor_elapsed_ms = elapsed_ms
        os.autoloop_anchor_abs_beat = abs_beat
        os.autoloop_anchor_bpm = bpm

    def _clear_autoloop_tempo_anchor(self) -> None:
        os = self._os
        os.autoloop_anchor_elapsed_ms = 0
        os.autoloop_anchor_abs_beat = 0.0
        os.autoloop_anchor_bpm = 0.0

    def _send_autoloop_deck_load(
        self,
        deck: int,
        mirror: int,
        active: int,
        arm_meta: TrackMetadata,
    ) -> None:
        # VDJ: active deck + mirror 1/2 + decks 3 and 4 all get the same track.
        for dk in (deck, mirror, 3, 4):
            self._out.send_deck_load(dk, arm_meta, active, play="on")

    def _schedule_autoloop_master_correction(
        self,
        deck: int,
        mirror: int,
        active: int,
        arm_meta: TrackMetadata,
        bpm: float,
        current_elapsed_ms: int,
        from_target_beat: int,
        source: str,
        reason: str,
    ) -> None:
        correction_meta = TrackMetadata(
            filepath=arm_meta.filepath,
            soundswitch_id=arm_meta.soundswitch_id,
            bpm=arm_meta.bpm,
            first_beat_ms=arm_meta.first_beat_ms,
            beatgrid_times_ms=list(arm_meta.beatgrid_times_ms),
            beatgrid_bpms=list(arm_meta.beatgrid_bpms),
            beatgrid_source=arm_meta.beatgrid_source,
            total_ms=arm_meta.total_ms,
            content_id=arm_meta.content_id,
        )
        target = int(from_target_beat) + AUTOLOOP_ARM_PHRASE_BEATS
        target_elapsed_ms, target_source = self._autoloop_target_elapsed_for_beat(
            target, current_elapsed_ms, bpm, correction_meta,
        )
        while target_elapsed_ms - current_elapsed_ms < _AUTOLOOP_PHRASE_MIN_RUNWAY_MS:
            target += AUTOLOOP_ARM_PHRASE_BEATS
            target_elapsed_ms, target_source = self._autoloop_target_elapsed_for_beat(
                target, current_elapsed_ms, bpm, correction_meta,
            )

        os = self._os
        os.autoloop_arm_pending = True
        os.autoloop_arm_pending_since = time.monotonic()
        os.autoloop_arm_sync_beat = target
        os.autoloop_arm_target_elapsed_ms = target_elapsed_ms
        os.autoloop_arm_target_source = target_source
        os.pending_autoloop_arm_meta = correction_meta
        os.pending_autoloop_arm_deck = deck
        os.pending_autoloop_arm_mirror = mirror
        os.pending_autoloop_arm_active = active
        os.pending_autoloop_arm_source = source
        os.pending_autoloop_arm_reason = f"correction-{reason}"
        log.info("[SS][AUTOLOOP-MASTER-CORRECTION-PENDING] deck=%d mirror=%d "
                 "reason=%s target_beat=%d target_elapsed_ms=%d until_ms=%d "
                 "grid_source=%s source=%s file=%s",
                 deck, mirror, reason, target, target_elapsed_ms,
                 target_elapsed_ms - current_elapsed_ms, target_source,
                 source or "<none>",
                 correction_meta.filepath.split("/")[-1] if correction_meta.filepath else "<none>")

    def _maybe_apply_live_bpm_follow(
        self,
        deck: int,
        mirror: int,
        timing_bpm: float,
        abs_beat_pos: float,
        now: float,
    ) -> float:
        os = self._os
        if not self._live_bpm_follow or os.lighting_mode != "autoloop":
            return timing_bpm
        if os.autoloop_arm_deck != deck or os.autoloop_arm_bpm <= 0:
            self._clear_live_bpm_follow()
            return timing_bpm
        if not os.was_playing:
            return timing_bpm
        if not self._deck[deck].playing:
            self._clear_live_bpm_follow()
            return timing_bpm

        live_bpm = self._live_bpm_value(deck)
        if live_bpm is None:
            return timing_bpm

        if abs(live_bpm - timing_bpm) <= _LIVE_BPM_FOLLOW_THRESHOLD:
            self._clear_live_bpm_follow()
            return timing_bpm

        if now - os.last_live_follow_send_mono < _LIVE_BPM_FOLLOW_SEND_INTERVAL_S:
            return timing_bpm

        os.pending_live_bpm = live_bpm
        return timing_bpm

    def _live_bpm_value(self, deck: int) -> Optional[float]:
        if self._live_bpm is None:
            return None
        try:
            live = self._live_bpm.get_bpm(deck)
        except Exception:
            log.debug("live BPM read failed", exc_info=True)
            return None
        if live is None or not math.isfinite(live) or live <= 0:
            return None
        return float(live)

    def _next_autoloop_arm_phrase(self, abs_beat_pos: float) -> int:
        """Calculate next phrase boundary for autoloop arm synchronization."""
        beat = max(1, int(abs_beat_pos) + 1)
        while beat % AUTOLOOP_ARM_PHRASE_BEATS != 0:
            beat += 1
        return beat

    def _previous_autoloop_arm_phrase(self, abs_beat_pos: float) -> int:
        beat = max(0, int(math.floor(abs_beat_pos)))
        return (beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS

    def _maybe_lock_autoloop_arm(
        self,
        active: int,
        mirror: int,
        bpm: float,
        abs_beat_pos: float,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        os = self._os
        if (
            os.lighting_mode != "autoloop"
            or os.autoloop_arm_deck != active
            or not os.autoloop_arm_pending
            or bpm <= 0
        ):
            return

        if os.autoloop_arm_sync_beat == 0:
            os.autoloop_arm_sync_beat = self._next_autoloop_arm_phrase(abs_beat_pos)
        if elapsed_ms is None:
            deck_elapsed = self._deck[active].elapsed_ms
            if deck_elapsed > 0:
                elapsed_ms = deck_elapsed
            elif bpm > 0:
                beat_ms = 60_000.0 / bpm
                elapsed_ms = int(round(self._deck[active].meta.first_beat_ms + (abs_beat_pos * beat_ms)))
            else:
                elapsed_ms = 0
        if os.autoloop_arm_target_elapsed_ms == 0:
            os.autoloop_arm_target_elapsed_ms, os.autoloop_arm_target_source = (
                self._autoloop_target_elapsed_for_beat(
                    os.autoloop_arm_sync_beat,
                    elapsed_ms,
                    bpm,
                    self._deck[active].meta,
                )
            )
            log.info("[SS][AUTOLOOP-ARM-PENDING] deck=%d current_beat=%.1f "
                     "current_elapsed_ms=%d target_beat=%d target_elapsed_ms=%d "
                     "until_ms=%d grid_source=%s",
                     active, abs_beat_pos, elapsed_ms, os.autoloop_arm_sync_beat,
                     os.autoloop_arm_target_elapsed_ms,
                     os.autoloop_arm_target_elapsed_ms - elapsed_ms,
                     os.autoloop_arm_target_source or "fallback")

        if elapsed_ms < os.autoloop_arm_target_elapsed_ms:
            return

        current_beat = int(abs_beat_pos)
        target_beat = os.autoloop_arm_sync_beat
        target_elapsed_ms = os.autoloop_arm_target_elapsed_ms
        target_source = os.autoloop_arm_target_source or "fallback"
        lateness_ms = max(0, elapsed_ms - target_elapsed_ms)
        arm_bpm = os.autoloop_arm_bpm if os.autoloop_arm_bpm > 0 else bpm
        pending_meta = os.pending_autoloop_arm_meta
        scheduled_correction = False
        if pending_meta is not None:
            pending_source = os.pending_autoloop_arm_source or "<none>"
            pending_reason = os.pending_autoloop_arm_reason or "scheduled"
            needs_correction = (
                pending_reason == "short-runway"
                or lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS
            )
            arm_elapsed_ms = elapsed_ms if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS else target_elapsed_ms
            object.__setattr__(pending_meta, "elapsed_ms", arm_elapsed_ms)
            if pending_reason.startswith("correction-"):
                for dk in (active, mirror, 3, 4):
                    self._out.send_deck_clear(dk)
                    self._out.send_loop_off(dk)
                log.info("[SS][AUTOLOOP-MASTER-CORRECTION-CLEAR] deck=%d mirror=%d "
                         "target_beat=%d reason=%s",
                         active, mirror, target_beat, pending_reason)
            self._send_autoloop_deck_load(
                os.pending_autoloop_arm_deck or active,
                os.pending_autoloop_arm_mirror or mirror,
                os.pending_autoloop_arm_active or active,
                pending_meta,
            )
            os.autoloop_change_on_next_beat = False
            log.info("[SS][AUTOLOOP-MASTER-ARM-LOCKED] deck=%d target_beat=%d "
                     "target_elapsed_ms=%d actual_elapsed_ms=%d lateness_ms=%d "
                     "tolerance_ms=%d grid_source=%s current_beat=%.1f "
                     "bpm=%.2f source=%s reason=%s correction=%s",
                     active, target_beat, target_elapsed_ms, elapsed_ms, lateness_ms,
                     _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS, target_source,
                     abs_beat_pos, arm_bpm, pending_source, pending_reason,
                     needs_correction)
            self._clear_pending_autoloop_master_phrase_arm()
            if needs_correction:
                reason = "late" if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS else "short-runway"
                self._schedule_autoloop_master_correction(
                    active, mirror, active, pending_meta, arm_bpm, elapsed_ms,
                    target_beat, pending_source, reason,
                )
                scheduled_correction = True
                if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
                    log.warning("[SS][AUTOLOOP-MASTER-ARM-LATE-CORRECTION] deck=%d "
                                "target_beat=%d target_elapsed_ms=%d "
                                "current_elapsed_ms=%d lateness_ms=%d "
                                "tolerance_ms=%d current_beat=%.1f grid_source=%s",
                                active, target_beat, target_elapsed_ms, elapsed_ms,
                                lateness_ms, _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS,
                                abs_beat_pos, target_source)
        elif lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
            log.warning("[SS][AUTOLOOP-PHRASE-MISS] deck=%d target_beat=%d "
                        "target_elapsed_ms=%d current_elapsed_ms=%d "
                        "lateness_ms=%d tolerance_ms=%d current_beat=%.1f "
                        "grid_source=%s",
                        active, target_beat, target_elapsed_ms, elapsed_ms,
                        lateness_ms, _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS,
                        abs_beat_pos, target_source)
        for dk in (active, mirror, 3, 4):
            self._out.send_bpm(dk, arm_bpm)
        os.last_sent_bpm = arm_bpm
        if not scheduled_correction:
            os.autoloop_arm_pending = False
            os.autoloop_arm_sync_beat = 0
            os.autoloop_arm_target_elapsed_ms = 0
            os.autoloop_arm_target_source = ""
            os.autoloop_arm_pending_since = 0.0
        log.info("[SS][AUTOLOOP-ARM-LOCKED] deck=%d target_beat=%d "
                 "send_elapsed_ms=%d lateness_ms=%d tolerance_ms=%d bpm=%.2f",
                 active, target_beat, elapsed_ms, lateness_ms,
                 _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS, arm_bpm)

    def _clear_autoloop_arm_phrase_lock(self) -> None:
        os = self._os
        os.autoloop_arm_pending = False
        os.autoloop_arm_sync_beat = 0
        os.autoloop_arm_target_elapsed_ms = 0
        os.autoloop_arm_target_source = ""
        os.autoloop_arm_pending_since = 0.0

    def _clear_live_bpm_follow(self) -> None:
        os = self._os
        os.pending_live_bpm = 0.0

    def _clear_autoloop_tempo_relock(self) -> None:
        self._os.autoloop_change_on_next_beat = False

    def _clear_pending_autoloop_master_phrase_arm(self) -> None:
        os = self._os
        os.pending_autoloop_arm_meta = None
        os.pending_autoloop_arm_deck = 0
        os.pending_autoloop_arm_mirror = 0
        os.pending_autoloop_arm_active = 0
        os.pending_autoloop_arm_source = ""
        os.pending_autoloop_arm_reason = ""

    def _autoloop_arm_bpm(self, deck: int, fallback_bpm: float) -> tuple[float, str]:
        live = self._live_bpm_value(deck)
        if live is not None:
            return live, "live"
        return fallback_bpm, "fallback"

    def _live_bpm_status_text(self, deck: int) -> str:
        if self._live_bpm is None:
            return "live_bpm=unavailable"
        try:
            status = self._live_bpm.get_status(deck)
        except Exception:
            log.debug("live BPM status read failed", exc_info=True)
            status = None
        if status is None:
            return "live_bpm=fallback_meta live_source=fallback_meta"
        age_ms = (time.monotonic() - status.updated_at) * 1000.0
        source = getattr(status, "source", "unknown")
        return (
            f"live_bpm={status.bpm:.2f} "
            f"live_source={source} "
            f"live_age_ms={age_ms:.0f} "
            f"live_addr=0x{status.addr:x}/{status.type_name}"
        )

    def _live_bpm_follow_status_text(self) -> str:
        os = self._os
        if not self._live_bpm_follow:
            return "follow=off"
        if os.pending_live_bpm > 0:
            return f"follow=on pending_bpm={os.pending_live_bpm:.2f}"
        return "follow=on gated_bpm=active"

    # ── Instrumentation ───────────────────────────────────────────────────────

    def _log_status(self) -> None:
        active = self._os.active_deck
        for dk in (1, 2):
            d = self._deck[dk]
            mark = "►" if dk == active else " "
            snap = self._cache.get(dk)
            pos_s = f"{snap.elapsed_ms}ms" if snap else "no-snap"
            log.info("%s D%d  %s  bpm=%.1f  pos=%s  %s",
                     mark, dk,
                     d.meta.filepath.split("/")[-1] if d.meta.filepath else "<empty>",
                     d.meta.bpm, pos_s,
                     ("scripted" if d.scripted_id else "autoloop") if d.playing else "stopped")
