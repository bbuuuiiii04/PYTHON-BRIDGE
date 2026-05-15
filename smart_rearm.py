from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import PHRASE_ANCHOR_BEATS
from .models import DeckState, OutputState
from .smart_phrasing import SmartPhrasingState

log = logging.getLogger("state_manager")


@dataclass(frozen=True)
class SmartDropTickResult:
    """Typed smart-drop tick status for StateManager/laser context plumbing."""

    crossing: bool
    blackout_armed: bool
    target_beat: Optional[int] = None

    @classmethod
    def none(cls) -> "SmartDropTickResult":
        return cls(crossing=False, blackout_armed=False)


@dataclass(frozen=True)
class SmartRearmTickResult:
    drop: SmartDropTickResult
    breakdown_fired: bool
    phrase_anchor_fired: bool


@dataclass(frozen=True)
class SmartRearmContext:
    mirror: int
    bpm: float
    this_beat: int
    elapsed_ms: int
    abs_beat_pos: float
    blackout_mode: bool
    smart_drop_enabled: bool
    smart_breakdown_enabled: bool
    phrase_anchor_enabled: bool
    lighting_mode_is_autoloop: bool


class SmartRearmCoordinator:
    def __init__(
        self,
        *,
        output_state_ref: Callable[[], OutputState],
        deck_ref: Callable[[int], DeckState],
        send_direct_autoloop_rearm: Callable[..., None],
        send_smart_transition_clear: Callable[..., None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._output_state_ref = output_state_ref
        self._deck_ref = deck_ref
        self._send_direct_autoloop_rearm = send_direct_autoloop_rearm
        self._send_smart_transition_clear = send_smart_transition_clear
        self._clock = clock

    def tick(
        self,
        active_deck: int,
        sp_state: SmartPhrasingState,
        ctx: SmartRearmContext,
    ) -> SmartRearmTickResult:
        if not ctx.lighting_mode_is_autoloop:
            return SmartRearmTickResult(
                drop=SmartDropTickResult.none(),
                breakdown_fired=False,
                phrase_anchor_fired=False,
            )

        drop = SmartDropTickResult.none()
        breakdown_fired = False
        phrase_anchor_fired = False

        if ctx.smart_drop_enabled:
            drop = self._drop(active_deck, sp_state, ctx)
        if ctx.smart_breakdown_enabled:
            breakdown_fired = self._breakdown(active_deck, sp_state, ctx)
        if ctx.phrase_anchor_enabled:
            phrase_anchor_fired = self._phrase_anchor(active_deck, sp_state, ctx)

        return SmartRearmTickResult(
            drop=drop,
            breakdown_fired=breakdown_fired,
            phrase_anchor_fired=phrase_anchor_fired,
        )

    def _drop(
        self,
        active: int,
        sp_state: SmartPhrasingState,
        ctx: SmartRearmContext,
    ) -> SmartDropTickResult:
        """Fire smart-drop cut before a detected drop, then rearm on the drop beat."""
        os = self._output_state_ref()

        if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
            return SmartDropTickResult.none()

        if os.breakdown_active:
            return SmartDropTickResult.none()

        target_beat: Optional[int]
        if os.drop_cut_armed:
            if sp_state.smart_drop_crossing:
                if sp_state.active_drop_beat is not None:
                    target_beat = int(sp_state.active_drop_beat)
                elif os.drop_rearm_beat:
                    target_beat = int(os.drop_rearm_beat)
                else:
                    target_beat = None
                if target_beat is None:
                    log.warning(
                        "[SM] smart-drop-crossing-no-target  deck=%d  beat=%d"
                        "  rearm_beat=%d  active_drop_beat=%s",
                        active,
                        ctx.this_beat,
                        os.drop_rearm_beat,
                        sp_state.active_drop_beat,
                    )
                    return SmartDropTickResult.none()
                if ctx.blackout_mode:
                    log.info(
                        "[SM] smart-drop-crossing  deck=%d  beat=%d  drop_at=%d",
                        active,
                        ctx.this_beat,
                        target_beat,
                    )
                    return SmartDropTickResult(
                        crossing=True,
                        blackout_armed=False,
                        target_beat=target_beat,
                    )
                log.info("[SM] smart-drop-rearm  deck=%d  beat=%d", active, ctx.this_beat)
                if self._send_direct_autoloop_rearm(
                    active,
                    ctx.mirror,
                    ctx.bpm,
                    ctx.elapsed_ms,
                    "smart-drop",
                    target_beat=target_beat,
                ):
                    os.phrase_anchor_last_beat = target_beat
                    os.drop_cut_armed = False
                    os.drop_rearm_beat = 0
                    return SmartDropTickResult(
                        crossing=True,
                        blackout_armed=False,
                        target_beat=target_beat,
                    )
            return SmartDropTickResult.none()

        if (
            sp_state.transition_mask_should_arm
            and sp_state.next_smart_drop_beat is not None
        ):
            drop_beat_int = int(sp_state.next_smart_drop_beat)
            if ctx.blackout_mode:
                log.info(
                    "[SM] smart-drop-blackout-arm  deck=%d  beat=%d  drop_at=%d",
                    active,
                    ctx.this_beat,
                    drop_beat_int,
                )
            else:
                log.info(
                    "[SM] smart-drop-cut  deck=%d  beat=%d  drop_at=%d",
                    active,
                    ctx.this_beat,
                    drop_beat_int,
                )
                self._send_smart_transition_clear(active)
            os.drop_cut_armed = True
            os.drop_rearm_beat = drop_beat_int
            return SmartDropTickResult(
                crossing=False,
                blackout_armed=True,
                target_beat=drop_beat_int,
            )
        return SmartDropTickResult.none()

    def _breakdown(
        self,
        active: int,
        sp_state: SmartPhrasingState,
        ctx: SmartRearmContext,
    ) -> bool:
        os = self._output_state_ref()

        if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
            return False

        if os.drop_cut_armed:
            return False

        if os.breakdown_active:
            if sp_state.breakdown_end_crossing:
                log.info(
                    "[SM] smart-breakdown-restore  deck=%d  beat=%d",
                    active,
                    ctx.this_beat,
                )
                if self._send_direct_autoloop_rearm(
                    active,
                    ctx.mirror,
                    ctx.bpm,
                    ctx.elapsed_ms,
                    "smart-breakdown",
                    target_beat=os.breakdown_restore_beat,
                ):
                    os.phrase_anchor_last_beat = os.breakdown_restore_beat
                    os.breakdown_active = False
                    os.breakdown_restore_beat = 0
                    return True
            return False

        if (
            sp_state.breakdown_start_crossing
            and sp_state.breakdown_restore_beat is not None
        ):
            log.info(
                "[SM] smart-breakdown-cut  deck=%d  beat=%d",
                active,
                ctx.this_beat,
            )
            self._send_smart_transition_clear(active)
            os.breakdown_active = True
            os.breakdown_restore_beat = int(sp_state.breakdown_restore_beat)
        return False

    def _phrase_anchor(
        self,
        active: int,
        sp_state: SmartPhrasingState,
        ctx: SmartRearmContext,
    ) -> bool:
        """Rearm autoloop every PHRASE_ANCHOR_BEATS to correct phrasing drift."""
        os = self._output_state_ref()

        if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
            return False

        if os.drop_cut_armed:
            return False

        if os.breakdown_active:
            return False

        target = sp_state.phrase_anchor_target_beat
        if target is None:
            if os.phrase_anchor_last_beat < 0:
                os.phrase_anchor_last_beat = (
                    int(ctx.abs_beat_pos) // PHRASE_ANCHOR_BEATS
                ) * PHRASE_ANCHOR_BEATS
            return False

        if ctx.this_beat > target + 8:
            os.phrase_anchor_last_beat = ctx.this_beat
            return False

        if sp_state.phrase_anchor_preclear_requested:
            log.info(
                "[SM] phrase-anchor-clear  deck=%d  beat=%d  anchor=%d",
                active,
                ctx.this_beat,
                target,
            )
            self._send_smart_transition_clear(active)
            return False

        if sp_state.phrase_anchor_rearm_requested:
            log.info(
                "[SM] phrase-anchor  deck=%d  beat=%d  anchor=%d",
                active,
                ctx.this_beat,
                target,
            )
            if self._send_direct_autoloop_rearm(
                active,
                ctx.mirror,
                ctx.bpm,
                ctx.elapsed_ms,
                "phrase-anchor",
                target_beat=target,
            ):
                os.phrase_anchor_last_beat = target
                return True
        return False
