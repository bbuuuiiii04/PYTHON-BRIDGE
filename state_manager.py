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

import logging
import math
import queue
import threading
import time
from typing import Optional

from .config import (
    AUTOLOOP_BEATS, ARM_GUARD_S, STOP_DEBOUNCE_S,
    PLAY_SETTLE_MS, TIMING_COMPENSATION_MS,
    BPM_THRESHOLD_SCRIPTED, BPM_THRESHOLD_UNSCRIPTED,
    MEM_STALE_S,
)
from .models import ArmSequence, BridgeEvent, DeckState, Ev, OutputState, PositionSnapshot, TrackMetadata
from .osl_output import OS2LOutput
from .rb_memory import PositionCache
from .scripted_tracks import SCRIPTED_TRACKS, lookup as st_lookup

log = logging.getLogger("state_manager")


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
    ) -> None:
        self._eq    = event_queue
        self._cache = position_cache
        self._out   = output
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

        # Ableton Link reader (optional — None if aalink unavailable)
        self._link = None

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

    def set_initial_state(self, active_deck: int) -> None:
        """Apply startup state read from TL ENGINE STATE before event loop starts."""
        if active_deck in (1, 2):
            self._os.active_deck = active_deck
            log.info("StateManager: initial active_deck=%d (from TL ENGINE STATE)", active_deck)

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
                self._handle_event(ev)
            except Exception:
                log.exception("StateManager: error handling %s", ev.kind)

    # ── Event dispatch ────────────────────────────────────────────────────────

    def _handle_event(self, ev: BridgeEvent) -> None:
        log.debug("event: kind=%s deck=%d src=%s payload=%s",
                  ev.kind, ev.deck, ev.source, ev.payload)
        d = ev.deck

        if ev.kind == Ev.MASTER_CHANGED:
            self._on_master_changed(d, ev.source)

        elif ev.kind == Ev.TRACK_LOADED:
            self._on_track_loaded(d, ev.payload.get("title", ""))

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

    # ── Deck switch ───────────────────────────────────────────────────────────

    def _on_master_changed(self, new_deck: int, source: str) -> None:
        old_deck = self._os.active_deck
        if new_deck == old_deck:
            return
        log.info("[D%d→D%d] deck switch  source=%s", old_deck, new_deck, source)
        # OSC race fix: TL's /bridge/active_deck can arrive after /bridge/track_loaded,
        # so SCRIPTED_ARM may land on the old active deck. If old deck wasn't playing
        # and new deck has no scripted_id, transfer it.
        old_d = self._deck[old_deck]
        new_d = self._deck[new_deck]
        if old_d.scripted_id > 0 and new_d.scripted_id == 0 and not old_d.playing:
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

    # ── Track load → lsof trigger ─────────────────────────────────────────────

    def _on_track_loaded(self, deck: int, title: str) -> None:
        d = self._deck[deck]
        d.meta.clear()
        d.scripted_id = 0
        d.load_gen += 1
        d.tl_title = title
        self._last_loaded_deck = deck
        log.info("[D%d] loaded: %s", deck, title or "<unknown>")

        if self._resolver is None:
            return

        # Prefer ANLZ-based resolution (no subprocess, fires before this event)
        anlz_path = self._pending_anlz_path.pop(deck, None)
        if anlz_path:
            log.debug("track load: deck %d using ANLZ path for resolution", deck)
            self._resolver.resolve_by_anlz(deck, d.load_gen, anlz_path)
        else:
            other = 3 - deck
            other_path = self._deck[other].meta.filepath
            # Fire both: lsof (fast, uses track length) and title-based DB lookup
            # (reliable fallback when memory track_length=0 prevents lsof from matching)
            self._resolver.resolve_async(deck, d.load_gen, other_path)
            if title:
                self._resolver.resolve_by_title(deck, d.load_gen, title)

    def attach_resolver(self, resolver) -> None:  # type: ignore[type-arg]
        self._resolver = resolver

    def attach_link(self, link) -> None:
        self._link = link

    # ── Filepath resolved ─────────────────────────────────────────────────────

    def _on_filepath_resolved(self, deck: int, payload: dict) -> None:
        d = self._deck[deck]
        gen = payload.get("load_gen", -1)
        if gen != d.load_gen:
            log.debug("lsof deck %d: stale result gen=%d current=%d — discarding",
                      deck, gen, d.load_gen)
            return

        meta = d.meta
        meta.filepath       = payload["filepath"]
        meta.bpm            = payload["bpm"]
        meta.content_id     = payload["content_id"]
        meta.first_beat_ms  = payload["first_beat_ms"]
        meta.soundswitch_id = payload["soundswitch_id"]
        meta.total_ms       = payload["total_ms"]

        log.info("[D%d] resolved: %s  bpm=%.1f  ssid=%s",
                 deck, payload["filepath"].split("/")[-1], meta.bpm,
                 "✓" if meta.soundswitch_id else "✗")

    # ── Scripted arm / clear ──────────────────────────────────────────────────

    def _arm_scripted(self, deck: int, track_id: int) -> None:
        # FM-1: non-blocking two-phase arm — no time.sleep() in push loop thread
        track = st_lookup(track_id)
        if not track:
            log.warning("[SS] arm scripted: unknown id=%d deck=%d", track_id, deck)
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

        log.info("[SS] arm scripted: id=%d  %s  deck=%d  elapsed=%dms",
                 track_id, track["filepath"].split("/")[-1] if track["filepath"] else "?",
                 deck, elapsed_ms)

        # Phase 0 (immediate): clear all 4 SS deck slots, stop playback + any autoloop
        for dk in (deck, mirror, 3, 4):
            self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            self._out.send_loop_off(dk)
            self._out.send_deck_play(dk, "off")

        # Phase 1 (scheduled): send_deck_load after SS has processed the clear
        arm_meta = TrackMetadata(
            filepath=d.meta.filepath, soundswitch_id=d.meta.soundswitch_id,
            bpm=d.meta.bpm, first_beat_ms=d.meta.first_beat_ms, total_ms=d.meta.total_ms,
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
            # Arm the scripted show. _arm_scripted is internally debounced (2 s)
            # so rapid pause/resume doesn't cause a full re-arm sequence.
            self._arm_scripted(deck, d.scripted_id)

        elif mode == "autoloop":
            self._pending_arm = None
            self._os.push_reset_bpm = True
            for dk in (deck, mirror, 3, 4):
                self._out._sub(f"deck {dk} get_filepath", "", verbose=True)
            if d.meta.filepath:
                self._os.last_armed_filepath = d.meta.filepath
                arm_meta = TrackMetadata(
                    filepath=d.meta.filepath,
                    soundswitch_id="",
                    bpm=d.meta.bpm,
                    first_beat_ms=d.meta.first_beat_ms,
                    total_ms=d.meta.total_ms,
                )
                object.__setattr__(arm_meta, "elapsed_ms", elapsed_ms)
                # VDJ: active deck + mirror 1/2 + decks 3 and 4 all get the same track
                for dk in (deck, mirror, 3, 4):
                    self._out.send_deck_load(dk, arm_meta, deck, play="on")
            else:
                self._os.last_armed_filepath = ""
                for dk in (deck, mirror):
                    self._deck[dk].meta.first_beat_ms = 0.0
                for dk in (deck, mirror, 3, 4):
                    self._out.send_loop_on(dk)
                    self._out._sub(f"deck {dk} play", "on", verbose=True)

        elif mode == "idle":
            self._pending_arm = None
            self._os.last_armed_filepath = ""
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
            if tl_ms > 0 and tl_at > 0:
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
        if os.push_reset_bpm:
            os.last_sent_bpm = 0.0
            os.push_reset_bpm = False

        # Beat position: computed from ENGINE STATE BPM (pitch-adjusted every ~15s).
        # Ableton Link phase is not used: if Link session tempo doesn't reflect
        # real-time pitch adjustments, phase drifts from the actual beat too.
        beat_pos = _compute_beat_pos(elapsed_ms, bpm, d.meta.first_beat_ms) if bpm > 0 else 0.0

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
        if bpm > 0:
            beat_ms = 60_000.0 / bpm
            beats_elapsed = (elapsed_ms - d.meta.first_beat_ms) / beat_ms
            this_beat = int(beats_elapsed)
            last_beat = int((os.last_beat_elapsed_ms - d.meta.first_beat_ms) / beat_ms) if beat_ms > 0 else 0

            if this_beat > last_beat:
                beat_index = this_beat % 4
                os.last_beat_elapsed_ms = elapsed_ms
                for dk in (active, mirror, 3, 4):
                    self._out.send_beat(dk, bpm, beat_index, change=(beat_index == 0))

        # Elapsed + beatpos — send at every push tick (SS needs continuous updates)
        for dk in (active, mirror, 3, 4):
            self._out.send_elapsed(dk, elapsed_ms, beat_pos)

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
        self._log_status()

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

