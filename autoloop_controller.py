from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import bridge_fmt as bf
from .beat_math import (
    _beatgrid_elapsed_for_abs_beat,
    _compute_beatgrid_position,
)
from .config import (
    AUTOLOOP_ARM_PHRASE_BEATS,
    AUTOLOOP_BEATS,
    BPM_THRESHOLD_UNSCRIPTED,
    STOP_DEBOUNCE_S,
)
from .models import DeckState, OutputState, TrackMetadata

_AUTOLOOP_IDLE_DEBOUNCE_S = max(STOP_DEBOUNCE_S, 2.0)
_AUTOLOOP_MASTER_PHRASE_START_GRACE_BEATS = 0.5
_AUTOLOOP_PHRASE_LATE_TOLERANCE_MS = 125
_AUTOLOOP_PHRASE_MIN_RUNWAY_MS = 1000
_LIVE_BPM_FOLLOW_THRESHOLD = BPM_THRESHOLD_UNSCRIPTED
_LIVE_BPM_FOLLOW_SEND_INTERVAL_S = 0.10


@dataclass(frozen=True)
class AutoloopTickContext:
    active: int
    mirror: int
    bpm: float
    abs_beat_pos: float
    elapsed_ms: Optional[int] = None


@dataclass(frozen=True)
class AutoloopTickResult:
    arm_locked: bool
    pending_before: bool
    pending_after: bool


class AutoloopController:
    def __init__(
        self,
        *,
        output_state_ref: Callable[[], OutputState],
        deck_ref: Callable[[int], DeckState],
        live_bpm_service,
        sse,
        logger: logging.Logger,
        clock: Callable[[], float] = time.monotonic,
        live_bpm_follow: bool = True,
        recorder_ref: Optional[Callable[[], object]] = None,
    ) -> None:
        self._output_state_ref = output_state_ref
        self._deck_ref = deck_ref
        self._live_bpm = live_bpm_service
        self._sse = sse
        self._clock = clock
        self._log = logger
        self._live_bpm_follow = live_bpm_follow
        self._recorder_ref = recorder_ref or (lambda: None)

    def tick(self, now: float, ctx: AutoloopTickContext) -> AutoloopTickResult:
        del now
        os = self._output_state_ref()
        pending_before = os.autoloop_arm_pending
        self._maybe_lock_autoloop_arm(
            ctx.active,
            ctx.mirror,
            ctx.bpm,
            ctx.abs_beat_pos,
            ctx.elapsed_ms,
        )
        pending_after = os.autoloop_arm_pending
        return AutoloopTickResult(
            arm_locked=bool(pending_before and not pending_after),
            pending_before=pending_before,
            pending_after=pending_after,
        )

    @property
    def idle_debounce_s(self) -> float:
        return _AUTOLOOP_IDLE_DEBOUNCE_S

    def apply_live_bpm_follow(
        self,
        deck: int,
        mirror: int,
        timing_bpm: float,
        abs_beat_pos: float,
        now: float,
    ) -> float:
        del mirror, abs_beat_pos
        os = self._output_state_ref()
        if not self._live_bpm_follow or os.lighting_mode != "autoloop":
            return timing_bpm
        if os.autoloop_arm_deck != deck or os.autoloop_arm_bpm <= 0:
            self.clear_live_bpm_follow()
            return timing_bpm
        if not os.was_playing:
            return timing_bpm
        if not self._deck_ref(deck).playing:
            self.clear_live_bpm_follow()
            return timing_bpm

        live_bpm = self.live_bpm_value(deck)
        if live_bpm is None:
            return timing_bpm

        if abs(live_bpm - timing_bpm) <= _LIVE_BPM_FOLLOW_THRESHOLD:
            self.clear_live_bpm_follow()
            return timing_bpm

        if now - os.last_live_follow_send_mono < _LIVE_BPM_FOLLOW_SEND_INTERVAL_S:
            return timing_bpm

        os.pending_live_bpm = live_bpm
        return timing_bpm

    def live_bpm_value(self, deck: int) -> Optional[float]:
        if self._live_bpm is None:
            return None
        try:
            live = self._live_bpm.get_bpm(deck)
        except Exception:
            self._log.debug("live BPM read failed", exc_info=True)
            return None
        if live is None or not math.isfinite(live) or live <= 0:
            recorder = self._recorder_ref()
            if recorder:
                recorder.record_live_bpm(deck, None, self._live_bpm_status(deck))
            return None
        bpm = float(live)
        recorder = self._recorder_ref()
        if recorder:
            recorder.record_live_bpm(deck, bpm, self._live_bpm_status(deck))
        return bpm

    def arm_bpm(self, deck: int, fallback_bpm: float) -> tuple[float, str]:
        live = self.live_bpm_value(deck)
        if live is not None:
            return live, "live"
        return fallback_bpm, "fallback"

    def arm_autoloop(
        self,
        deck: int,
        elapsed_ms: int,
        bpm: float,
        autoloop_master_phrase_arm: bool,
    ) -> None:
        mirror = 3 - deck
        d = self._deck_ref(deck)
        os = self._output_state_ref()
        out = self._sse._out

        os.push_reset_bpm = True
        arm_bpm, bpm_source = self.arm_bpm(deck, d.meta.bpm)
        os.autoloop_arm_bpm = arm_bpm
        os.autoloop_arm_deck = deck
        os.autoloop_arm_pending = True
        os.autoloop_arm_sync_beat = 0
        os.autoloop_arm_pending_since = self._clock()
        os.last_autoloop_status_phrase_beat = 0
        self.clear_live_bpm_follow()
        self.clear_tempo_relock()
        self.clear_tempo_anchor()
        self.clear_pending_master_phrase_arm()
        os.last_live_follow_bpm = arm_bpm
        os.last_live_follow_send_mono = 0.0
        os.live_follow_generation += 1
        arm_after_master = os.autoloop_arm_after_master_change
        arm_source = os.autoloop_master_change_source
        os.autoloop_arm_after_master_change = False
        os.autoloop_master_change_source = ""
        self._log.info(
            "[SM] arm-autoloop  deck=%d  elapsed=%s  bpm=%.1f  src=%s  file=%s",
            deck,
            bf.elapsed(elapsed_ms),
            arm_bpm,
            bpm_source,
            bf.short(d.meta.filepath),
        )
        self._log.debug(
            "[SM] arm-autoloop  deck=%d  mirror=%d  loop=%d  meta_bpm=%.2f"
            "  after_master=%s  master_src=%s  prev=%s",
            deck,
            mirror,
            AUTOLOOP_BEATS,
            d.meta.bpm,
            arm_after_master,
            arm_source or "<none>",
            bf.short(os.last_armed_filepath),
        )
        if arm_after_master and autoloop_master_phrase_arm:
            self._sse.send_autoloop_clear(deck)
            self._log.info("[SM] clear-autoloop  deck=%d  src=%s", deck, arm_source or "<none>")
        else:
            for dk in self._sse.deck_route(deck):
                out._sub(f"deck {dk} get_filepath", "", verbose=True)
        if d.meta.filepath:
            os.last_armed_filepath = d.meta.filepath
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
            abs_beat = self.abs_beat_for_elapsed(elapsed_ms, arm_bpm, arm_meta)
            self.set_tempo_anchor(elapsed_ms, abs_beat, arm_bpm)
            if self.should_delay_master_arm(
                arm_after_master, autoloop_master_phrase_arm, abs_beat,
            ):
                target = self.next_arm_phrase(abs_beat)
                target_elapsed_ms, target_source = self.target_elapsed_for_beat(
                    target, elapsed_ms, arm_bpm, arm_meta,
                )
                pending_reason = "scheduled"
                if target_elapsed_ms - elapsed_ms < _AUTOLOOP_PHRASE_MIN_RUNWAY_MS:
                    pending_reason = "short-runway"
                os.autoloop_arm_sync_beat = target
                os.autoloop_arm_target_elapsed_ms = target_elapsed_ms
                os.autoloop_arm_target_source = target_source
                os.pending_autoloop_arm_meta = arm_meta
                os.pending_autoloop_arm_deck = deck
                os.pending_autoloop_arm_mirror = mirror
                os.pending_autoloop_arm_active = deck
                os.pending_autoloop_arm_source = arm_source or "master"
                os.pending_autoloop_arm_reason = pending_reason
                self._log.info(
                    "[SM] arm-pending  deck=%d  beat=%.1f→%d  until=%dms  file=%s",
                    deck,
                    abs_beat,
                    target,
                    target_elapsed_ms - elapsed_ms,
                    bf.short(d.meta.filepath),
                )
                self._log.debug(
                    "[SM] arm-pending  deck=%d  target_elapsed=%dms  grid=%s"
                    "  src=%s  reason=%s",
                    deck,
                    target_elapsed_ms,
                    target_source,
                    arm_source or "<none>",
                    pending_reason,
                )
            else:
                self._sse.send_autoloop_deck_load(deck, mirror, deck, arm_meta)
                if arm_after_master and autoloop_master_phrase_arm:
                    phrase_beat = self.previous_arm_phrase(abs_beat)
                    phrase_elapsed_ms, phrase_source = self.target_elapsed_for_beat(
                        phrase_beat, elapsed_ms, arm_bpm, arm_meta,
                    )
                    lateness_ms = max(0, elapsed_ms - phrase_elapsed_ms)
                    if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
                        self.schedule_master_correction(
                            deck,
                            mirror,
                            deck,
                            arm_meta,
                            arm_bpm,
                            elapsed_ms,
                            phrase_beat,
                            arm_source or "master",
                            "phrase-grace-late",
                        )
                        self._log.warning(
                            "[SS][AUTOLOOP-MASTER-ARM-GRACE-LATE]"
                            " [SM] arm-grace-late  deck=%d  beat=%d"
                            "  late=%dms  tolerance=%dms",
                            deck,
                            phrase_beat,
                            lateness_ms,
                            _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS,
                        )
        else:
            os.last_armed_filepath = ""
            for dk in (deck, mirror):
                self._deck_ref(dk).meta.first_beat_ms = 0.0
            abs_beat = self.abs_beat_for_elapsed(elapsed_ms, arm_bpm, d.meta)
            self.set_tempo_anchor(elapsed_ms, abs_beat, arm_bpm)
            for dk in self._sse.deck_route(deck):
                out.send_loop_on(dk)
                out._sub(f"deck {dk} play", "on", verbose=True)
        os.autoloop_arm_after_master_change = False
        os.autoloop_master_change_source = ""

    def live_bpm_status_text(self, deck: int) -> str:
        if self._live_bpm is None:
            return "live_bpm=unavailable"
        try:
            status = self._live_bpm.get_status(deck)
        except Exception:
            self._log.debug("live BPM status read failed", exc_info=True)
            status = None
        if status is None:
            return "live_bpm=fallback_meta live_source=fallback_meta"
        age_ms = (self._clock() - status.updated_at) * 1000.0
        source = getattr(status, "source", "unknown")
        return (
            f"live_bpm={status.bpm:.2f} "
            f"live_source={source} "
            f"live_age_ms={age_ms:.0f} "
            f"live_addr=0x{status.addr:x}/{status.type_name}"
        )

    def live_bpm_follow_status_text(self) -> str:
        os = self._output_state_ref()
        if not self._live_bpm_follow:
            return "follow=off"
        if os.pending_live_bpm > 0:
            return f"follow=on pending_bpm={os.pending_live_bpm:.2f}"
        return "follow=on gated_bpm=active"

    def log_autoloop_tick(
        self,
        active: int,
        elapsed_ms: int,
        beatpos_out: float,
        timing_bpm: float,
        meta_bpm: float,
        grid_status: str,
    ) -> None:
        os = self._output_state_ref()
        live_status = self.live_bpm_status_text(active)
        self._log.info(
            "[SS][AUTOLOOP-TICK] [SM] autoloop-tick  deck=%d  elapsed=%s  beat=%.2f"
            "  bpm=%.2f  arm_bpm=%.2f  meta_bpm=%.2f  grid=%s  %s  %s  file=%s",
            active,
            bf.elapsed(elapsed_ms),
            beatpos_out,
            timing_bpm,
            os.autoloop_arm_bpm,
            meta_bpm,
            grid_status,
            live_status,
            self.live_bpm_follow_status_text(),
            bf.short(os.last_armed_filepath),
        )

    def should_delay_master_arm(
        self,
        arm_after_master: bool,
        autoloop_master_phrase_arm: bool,
        abs_beat_pos: float,
    ) -> bool:
        if not autoloop_master_phrase_arm or not arm_after_master:
            return False
        return not self.is_near_phrase_start(abs_beat_pos)

    def is_near_phrase_start(self, abs_beat_pos: float) -> bool:
        phrase_offset = math.fmod(max(abs_beat_pos, 0.0), AUTOLOOP_ARM_PHRASE_BEATS)
        if phrase_offset < 0:
            phrase_offset += AUTOLOOP_ARM_PHRASE_BEATS
        return phrase_offset <= _AUTOLOOP_MASTER_PHRASE_START_GRACE_BEATS

    def abs_beat_for_elapsed(
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

    def target_elapsed_for_beat(
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
        os = self._output_state_ref()
        if os.autoloop_anchor_bpm > 0:
            elapsed_ms = os.autoloop_anchor_elapsed_ms + (
                (target_beat - os.autoloop_anchor_abs_beat) * beat_ms
            )
        else:
            elapsed_ms = meta.first_beat_ms + (target_beat * beat_ms)
        return int(round(elapsed_ms)), "fallback"

    def fallback_abs_beat_for_elapsed(
        self,
        deck: int,
        elapsed_ms: int,
        bpm: float,
        first_beat_ms: float,
    ) -> float:
        os = self._output_state_ref()
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

    def set_tempo_anchor(self, elapsed_ms: int, abs_beat: float, bpm: float) -> None:
        os = self._output_state_ref()
        os.autoloop_anchor_elapsed_ms = elapsed_ms
        os.autoloop_anchor_abs_beat = abs_beat
        os.autoloop_anchor_bpm = bpm

    def clear_tempo_anchor(self) -> None:
        os = self._output_state_ref()
        os.autoloop_anchor_elapsed_ms = 0
        os.autoloop_anchor_abs_beat = 0.0
        os.autoloop_anchor_bpm = 0.0

    def schedule_master_correction(
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
        target_elapsed_ms, target_source = self.target_elapsed_for_beat(
            target, current_elapsed_ms, bpm, correction_meta,
        )
        while target_elapsed_ms - current_elapsed_ms < _AUTOLOOP_PHRASE_MIN_RUNWAY_MS:
            target += AUTOLOOP_ARM_PHRASE_BEATS
            target_elapsed_ms, target_source = self.target_elapsed_for_beat(
                target, current_elapsed_ms, bpm, correction_meta,
            )

        os = self._output_state_ref()
        os.autoloop_arm_pending = True
        os.autoloop_arm_pending_since = self._clock()
        os.autoloop_arm_sync_beat = target
        os.autoloop_arm_target_elapsed_ms = target_elapsed_ms
        os.autoloop_arm_target_source = target_source
        os.pending_autoloop_arm_meta = correction_meta
        os.pending_autoloop_arm_deck = deck
        os.pending_autoloop_arm_mirror = mirror
        os.pending_autoloop_arm_active = active
        os.pending_autoloop_arm_source = source
        os.pending_autoloop_arm_reason = f"correction-{reason}"
        self._log.info(
            "[SM] arm-correction-pending  deck=%d  beat=%d  until=%dms"
            "  reason=%s  grid=%s  src=%s  file=%s",
            deck,
            target,
            target_elapsed_ms - current_elapsed_ms,
            reason,
            target_source,
            source or "<none>",
            bf.short(correction_meta.filepath),
        )

    def next_arm_phrase(self, abs_beat_pos: float) -> int:
        beat = max(1, int(abs_beat_pos) + 1)
        while beat % AUTOLOOP_ARM_PHRASE_BEATS != 0:
            beat += 1
        return beat

    def previous_arm_phrase(self, abs_beat_pos: float) -> int:
        beat = max(0, int(math.floor(abs_beat_pos)))
        return (beat // AUTOLOOP_ARM_PHRASE_BEATS) * AUTOLOOP_ARM_PHRASE_BEATS

    def clear_arm_phrase_lock(self) -> None:
        os = self._output_state_ref()
        os.autoloop_arm_pending = False
        os.autoloop_arm_sync_beat = 0
        os.autoloop_arm_target_elapsed_ms = 0
        os.autoloop_arm_target_source = ""
        os.autoloop_arm_pending_since = 0.0

    def clear_live_bpm_follow(self) -> None:
        os = self._output_state_ref()
        os.pending_live_bpm = 0.0

    def clear_tempo_relock(self) -> None:
        self._output_state_ref().autoloop_change_on_next_beat = False

    def clear_pending_master_phrase_arm(self) -> None:
        os = self._output_state_ref()
        os.pending_autoloop_arm_meta = None
        os.pending_autoloop_arm_deck = 0
        os.pending_autoloop_arm_mirror = 0
        os.pending_autoloop_arm_active = 0
        os.pending_autoloop_arm_source = ""
        os.pending_autoloop_arm_reason = ""

    def _live_bpm_status(self, deck: int):
        if self._live_bpm is None:
            return None
        try:
            return self._live_bpm.get_status(deck)
        except Exception:
            return None

    def _maybe_lock_autoloop_arm(
        self,
        active: int,
        mirror: int,
        bpm: float,
        abs_beat_pos: float,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        os = self._output_state_ref()
        if (
            os.lighting_mode != "autoloop"
            or os.autoloop_arm_deck != active
            or not os.autoloop_arm_pending
            or bpm <= 0
        ):
            return

        if os.autoloop_arm_sync_beat == 0:
            os.autoloop_arm_sync_beat = self.next_arm_phrase(abs_beat_pos)
        if elapsed_ms is None:
            deck = self._deck_ref(active)
            deck_elapsed = deck.elapsed_ms
            if deck_elapsed > 0:
                elapsed_ms = deck_elapsed
            elif bpm > 0:
                beat_ms = 60_000.0 / bpm
                elapsed_ms = int(round(deck.meta.first_beat_ms + (abs_beat_pos * beat_ms)))
            else:
                elapsed_ms = 0
        if os.autoloop_arm_target_elapsed_ms == 0:
            os.autoloop_arm_target_elapsed_ms, os.autoloop_arm_target_source = (
                self.target_elapsed_for_beat(
                    os.autoloop_arm_sync_beat,
                    elapsed_ms,
                    bpm,
                    self._deck_ref(active).meta,
                )
            )
            self._log.info(
                "[SM] arm-pending  deck=%d  beat=%.1f→%d  until=%dms  grid=%s",
                active,
                abs_beat_pos,
                os.autoloop_arm_sync_beat,
                os.autoloop_arm_target_elapsed_ms - elapsed_ms,
                os.autoloop_arm_target_source or "fallback",
            )

        if elapsed_ms < os.autoloop_arm_target_elapsed_ms:
            return

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
            arm_elapsed_ms = (
                elapsed_ms
                if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS
                else target_elapsed_ms
            )
            object.__setattr__(pending_meta, "elapsed_ms", arm_elapsed_ms)
            if pending_reason.startswith("correction-"):
                self._sse.send_autoloop_clear(active)
                self._log.info(
                    "[SM] arm-correction-clear  deck=%d  beat=%d  reason=%s",
                    active,
                    target_beat,
                    pending_reason,
                )
            self._sse.send_autoloop_deck_load(
                os.pending_autoloop_arm_deck or active,
                os.pending_autoloop_arm_mirror or mirror,
                os.pending_autoloop_arm_active or active,
                pending_meta,
            )
            os.autoloop_change_on_next_beat = False
            self._log.info(
                "[SM] arm-locked  deck=%d  beat=%d  late=%dms"
                "  bpm=%.2f  reason=%s  correction=%s  src=%s",
                active,
                target_beat,
                lateness_ms,
                arm_bpm,
                pending_reason,
                needs_correction,
                pending_source,
            )
            self.clear_pending_master_phrase_arm()
            if needs_correction:
                reason = (
                    "late"
                    if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS
                    else "short-runway"
                )
                self.schedule_master_correction(
                    active,
                    mirror,
                    active,
                    pending_meta,
                    arm_bpm,
                    elapsed_ms,
                    target_beat,
                    pending_source,
                    reason,
                )
                scheduled_correction = True
                if lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
                    self._log.warning(
                        "[SS][AUTOLOOP-MASTER-ARM-LATE-CORRECTION]"
                        " [SM] arm-late  deck=%d  beat=%d  late=%dms"
                        "  tolerance=%dms  grid=%s",
                        active,
                        target_beat,
                        lateness_ms,
                        _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS,
                        target_source,
                    )
        elif lateness_ms > _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS:
            self._log.warning(
                "[SS][AUTOLOOP-PHRASE-MISS]"
                " [SM] arm-phrase-miss  deck=%d  beat=%d  late=%dms"
                "  tolerance=%dms  grid=%s",
                active,
                target_beat,
                lateness_ms,
                _AUTOLOOP_PHRASE_LATE_TOLERANCE_MS,
                target_source,
            )
        self._sse.send_autoloop_bpm(active, arm_bpm)
        os.last_sent_bpm = arm_bpm
        if not scheduled_correction:
            os.autoloop_arm_pending = False
            os.autoloop_arm_sync_beat = 0
            os.autoloop_arm_target_elapsed_ms = 0
            os.autoloop_arm_target_source = ""
            os.autoloop_arm_pending_since = 0.0
        self._log.info(
            "[SM] arm-locked-final  deck=%d  beat=%d  late=%dms  bpm=%.2f",
            active,
            target_beat,
            lateness_ms,
            arm_bpm,
        )


def send_direct_autoloop_rearm(
    sm,
    active: int,
    mirror: int,
    bpm: float,
    elapsed_ms: int,
    reason: str,
    target_beat: Optional[int] = None,
) -> bool:
    d = sm._deck[active]
    if not d.meta.filepath:
        return False

    arm_bpm = sm._os.autoloop_arm_bpm if sm._os.autoloop_arm_bpm > 0 else bpm
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
    target_elapsed_ms = elapsed_ms
    target_source = "current"
    lateness_ms = 0
    if target_beat is not None:
        target_elapsed_ms, target_source = sm._autoloop.target_elapsed_for_beat(
            target_beat, elapsed_ms, arm_bpm, arm_meta,
        )
        lateness_ms = max(0, elapsed_ms - target_elapsed_ms)

    object.__setattr__(arm_meta, "elapsed_ms", target_elapsed_ms)
    sm._os.last_arm_mono = time.monotonic()
    sm._os.last_armed_filepath = d.meta.filepath
    sm._sse.send_autoloop_clear(active)
    sm._sse.send_autoloop_deck_load(active, mirror, active, arm_meta)
    sm._sse.send_autoloop_bpm(active, arm_bpm)
    sm._os.last_sent_bpm = arm_bpm
    logging.getLogger("state_manager").info(
        "[SM] autoloop-rearm  deck=%d  reason=%s  beat=%s  elapsed=%s"
        "  target_elapsed=%s  late=%dms  grid=%s  bpm=%.1f  file=%s",
        active,
        reason,
        target_beat if target_beat is not None else "-",
        bf.elapsed(elapsed_ms),
        bf.elapsed(target_elapsed_ms),
        lateness_ms,
        target_source,
        arm_bpm,
        bf.short(d.meta.filepath),
    )
    return True
