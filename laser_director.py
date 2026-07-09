"""LaserDirector — dry-run-only scene policy.

Observes bridge state via LaserContext, selects a scene based on priority
rules, and records the decision in status. Does not send MIDI. Does not call
OS2LOutput. Does not mutate DeckState.

tick() is bounded and non-blocking. All policy state is owned by this object
and must only be mutated from the StateManager thread after startup.

Role-to-scene mapping
---------------------
Role names are stable policy vocabulary. Actual scene names are arbitrary
operator-defined strings supplied at construction (or via a future config
loader). Defaults are:

  safe_scene      -> "safe_static"
  default_scene   -> "house_phrase_1"
  emergency_scene -> "emergency_blackout"

These defaults are not requirements. Any string is valid.

Priority order (dry-run Phase 1)
---------------------------------
1. Disabled              -> do nothing
2. Emergency blackout    -> emergency_scene (latched until cleared)
3. Manual override       -> provided scene name (expires after ttl_s)
4. Not playing / no track / stale / scripted / autoloop-not-ready -> no output
5. Automatic scenes      -> only when autoloop-ready and unscripted
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Literal, Optional

from . import bridge_log
from .laser_decision_log import LaserDecision, LaserDecisionLog
from .laser_models import LaserContext, LaserPersonality, LaserSceneDecision
from .smart_phrasing import SmartPhrasingState
from .drop_lifecycle import DropLifecycle, DropLifecycleConfig

log = logging.getLogger("laser_director")

# These are example scene names taken from the operator's early mapping notes
# (docs/guides/laser_director_midi_mapping_workflow.md). They are constructor defaults
# only — any arbitrary string is valid. A future config loader must supply its
# own values rather than relying on these constants.
_DEFAULT_SAFE_SCENE = "safe_static"
_DEFAULT_DEFAULT_SCENE = "house_phrase_1"
_DEFAULT_EMERGENCY_SCENE = "emergency_blackout"
_LASER_DROP_IMPACT_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})


class LaserDirector:
    """Dry-run laser scene policy director.

    Args:
        dry_run:        When True (default), decisions are logged/status-only;
                        no MIDI is sent (MidiOutput is not yet wired in Phase 1).
        enabled:        Start enabled. Defaults to False (safe default).
        safe_scene:     Scene name for the "safe" role.
        default_scene:  Scene name for the "default" role.
        emergency_scene: Scene name for the "emergency" role.
    """

    def __init__(
        self,
        *,
        dry_run: bool = True,
        enabled: bool = False,
        safe_scene: str = _DEFAULT_SAFE_SCENE,
        default_scene: str = _DEFAULT_DEFAULT_SCENE,
        emergency_scene: str = _DEFAULT_EMERGENCY_SCENE,
        phrase_scene: str = "",
        phrase_interval_beats: int = 32,
        minimum_scene_hold_beats: int = 0,
        normal_changes_only_on_phrase_boundary: bool = False,
        breakdown_scene: str = "",
        buildup_scene: str = "",
        drop_scene: str = "",
        post_drop_scene: str = "",
        buildup_lookahead_beats: int = 32,
        post_drop_hold_beats: int = 8,
        drop_style: str = "drop_mode",
        scenes: Optional[dict] = None,
    ) -> None:
        self._dry_run = dry_run
        self._enabled = enabled
        self._safe_scene = safe_scene
        self._default_scene = default_scene
        self._emergency_scene = emergency_scene
        self._phrase_scene = phrase_scene
        self._phrase_interval_beats = max(1, int(phrase_interval_beats))
        self._minimum_scene_hold_beats = max(0, int(minimum_scene_hold_beats))
        self._normal_changes_only_on_phrase_boundary = bool(
            normal_changes_only_on_phrase_boundary
        )
        self._breakdown_scene = breakdown_scene
        self._buildup_scene = buildup_scene
        self._drop_scene = drop_scene
        self._post_drop_scene = post_drop_scene
        self._buildup_lookahead_beats = max(0, int(buildup_lookahead_beats))
        self._post_drop_hold_beats = max(0, int(post_drop_hold_beats))
        self._drop_style = self._canon_drop_style(drop_style)
        self._scenes = scenes or {}

        # Mutable policy state — written only from the StateManager thread.
        self._emergency: bool = False
        self._manual_override_scene: Optional[str] = None
        self._manual_override_expires_at: float = 0.0
        self._current_scene: str = ""
        self._last_reason: str = ""
        self._last_error: str = ""
        self._personality: str = ""
        self._pending_personality: Optional[tuple[str, LaserPersonality]] = None
        self._personality_apply_callback: Optional[
            Callable[[str, LaserPersonality], None]
        ] = None
        self._last_phrase_number: Optional[int] = None
        self._last_scene_change_abs_beat: float = 0.0
        self._last_trigger_abs_beat: float = 0.0
        self._pending_drop_crossing_beat: Optional[int] = None
        self._drop_rearm_edge_seen_for_pending: bool = False
        self._post_drop_start_abs_beat: float = -1.0
        self._last_smart_abs_beat: Optional[float] = None
        self._phrase_trigger_pending: bool = False
        self._last_buildup_gate_log_key: Optional[tuple[object, ...]] = None
        self._smart_drop_blackout_active: bool = False
        self._decision_log = LaserDecisionLog()
        self._drop_lifecycle: Optional[DropLifecycle] = None
        self._drop_lifecycle_mirror: bool = True
        self._allow_high_impact: bool = False
        self._post_drop_bank: tuple[str, ...] = ()

    # ── Policy commands (called from StateManager._handle_event) ─────────────

    def is_enabled(self) -> bool:
        """Return current enabled state. Constant-time; safe to call from any thread."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def toggle_enabled(self) -> None:
        self._enabled = not self._enabled

    def set_manual_override(self, scene: str, ttl_s: float) -> None:
        """Set a manual scene override that expires after ttl_s seconds."""
        self._manual_override_scene = scene
        self._manual_override_expires_at = time.monotonic() + ttl_s

    def clear_manual_override(self) -> None:
        """Clear manual scene override. Does not clear emergency blackout."""
        self._manual_override_scene = None
        self._manual_override_expires_at = 0.0

    def set_emergency_blackout(self, active: bool) -> None:
        """Latch or unlatch emergency blackout."""
        self._emergency = bool(active)

    def clear_emergency_blackout(self) -> None:
        """Clear emergency blackout and the manual override (per safety spec)."""
        self._emergency = False
        self.clear_manual_override()

    def set_personality(self, personality: str) -> None:
        self._personality = personality

    def get_personality(self) -> str:
        return self._personality

    def set_personality_apply_callback(
        self,
        callback: Optional[Callable[[str, LaserPersonality], None]],
    ) -> None:
        self._personality_apply_callback = callback

    def queue_personality_change(
        self,
        personality: str,
        config: LaserPersonality,
    ) -> None:
        if personality == self._personality and self._pending_personality is None:
            return
        self._pending_personality = (personality, config)

    def set_personality_config(self, personality: LaserPersonality) -> None:
        """Load scene-role and timing settings from a validated personality."""
        self._phrase_scene = personality.phrase_scene
        self._phrase_interval_beats = max(1, int(personality.phrase_interval_beats))
        self._minimum_scene_hold_beats = max(
            0, int(personality.minimum_scene_hold_beats)
        )
        self._normal_changes_only_on_phrase_boundary = bool(
            personality.normal_changes_only_on_phrase_boundary
        )
        self._breakdown_scene = personality.breakdown_scene
        self._buildup_scene = personality.buildup_scene
        self._drop_scene = personality.drop_scene
        self._post_drop_scene = personality.post_drop_scene
        self._buildup_lookahead_beats = max(0, int(personality.buildup_lookahead_beats))
        self._post_drop_hold_beats = max(0, int(personality.post_drop_hold_beats))
        self._drop_style = self._canon_drop_style(
            getattr(personality, "drop_style", "drop_mode")
        )
        self._drop_lifecycle_mirror = bool(getattr(personality, "drop_lifecycle_mirror", True))
        self._allow_high_impact = bool(getattr(personality, "allow_high_impact", False))
        self._post_drop_bank = tuple(personality.post_drop_bank)
        self._drop_lifecycle = DropLifecycle(DropLifecycleConfig(
            max_drops_in_a_row=int(getattr(personality, "max_drops_in_a_row", 2)),
            drop_impact_beats=float(getattr(personality, "drop_impact_beats", 32.0)),
            post_drop_cycle_beats=float(getattr(personality, "post_drop_cycle_beats", 32.0)),
            impact_predecessors=_LASER_DROP_IMPACT_PREDECESSORS,
        ))

    @staticmethod
    def _canon_drop_style(value: object) -> str:
        style = str(value or "").strip().lower()
        return "emphasized_drop" if style == "emphasized_drop" else "drop_mode"

    # ── Tick (called from StateManager._push_tick) ────────────────────────────

    def tick(self, ctx: LaserContext, *, now: float) -> Optional[LaserSceneDecision]:
        """Evaluate policy for one tick. Bounded and non-blocking.

        Must not:
        - Send MIDI.
        - Call OS2LOutput.
        - Mutate DeckState.
        - Mutate existing OS2L OutputState.
        - Block on any I/O or queue operation.
        - Call conn.status().
        - Read config files.
        """
        if not self._enabled:
            return None

        self._smart_drop_blackout_active = bool(ctx.smart_drop_blackout_active)
        decision = self._decide(ctx, now=now)

        scene_changed = decision.scene != self._current_scene
        reason_changed = decision.reason != self._last_reason
        if scene_changed:
            self._record_decision(
                ctx,
                decision,
                now=now,
                triggered_by="scene_change",
            )
            bridge_log.perf(
                "laser.scene",
                "scene %s->%s (%s)",
                self._current_scene or "(none)",
                decision.scene,
                decision.reason,
                deck=ctx.active_deck,
                beat=ctx.abs_beat,
                data={
                    "scene": decision.scene,
                    "prev": self._current_scene,
                    "reason": decision.reason,
                    "role": decision.role,
                    "dry_run": self._dry_run,
                },
            )
        elif reason_changed:
            self._record_decision(
                ctx,
                decision,
                now=now,
                triggered_by="reason_update",
            )
            log.debug(
                "[LASER] reason-update  scene=%s  reason=%s->%s",
                decision.scene or "(none)",
                self._last_reason or "(none)",
                decision.reason,
            )

        if scene_changed and decision.scene:
            self._last_trigger_abs_beat = max(ctx.abs_beat, 0.0)

        if (
            scene_changed
            and decision.reason in ("default", "default_init", "phrase_boundary")
            and self._is_normal_auto_scene(decision.scene)
        ):
            self._last_scene_change_abs_beat = max(ctx.abs_beat, 0.0)

        self._current_scene = decision.scene
        self._last_reason = decision.reason
        return decision

    def _record_decision(
        self,
        ctx: LaserContext,
        decision: LaserSceneDecision,
        *,
        now: float,
        triggered_by: Literal["scene_change", "reason_update"],
    ) -> None:
        self._decision_log.record(
            LaserDecision(
                mono=now,
                wall=time.time(),
                scene=decision.scene,
                prev_scene=self._current_scene,
                reason=decision.reason,
                abs_beat=ctx.abs_beat,
                deck=ctx.active_deck,
                personality=self._personality,
                lighting_mode=ctx.lighting_mode,
                triggered_by=triggered_by,
            )
        )

    def _has_usable_cyclable_post_drop(self) -> bool:
        for name in self._post_drop_bank:
            sd = self._scenes.get(name)
            if sd is None:
                continue
            if sd.scene_type != "autoloop":
                continue
            if sd.safety_class == "high_impact" and not self._allow_high_impact:
                continue
            return True
        return False

    @staticmethod
    def _laser_runway_ok(anlz_buildups, drop_beat: float) -> bool:
        """Part I: a drop earns laser drop scenes only if a bridge-defined buildup
        marker sits strictly before it. Fail-open when the track has NO buildup
        markers at all — an absent analysis and a genuinely marker-free track both
        leave meta.anlz_buildups empty, so an empty list can never mean 'suppress'.
        """
        if not anlz_buildups:
            return True
        return any(float(b) < drop_beat for b in anlz_buildups)

    def _laser_drop_runway_suppressed(self, ctx: LaserContext, sp, previous_abs_beat) -> bool:
        """True only on a NEW drop crossing whose drop beat has no buildup marker
        before it. Mirrors the two drop-fire paths' crossing detection. Returns
        False on the first smart tick (no crossing fires there) and whenever the
        track has no buildup data (fail-open)."""
        if previous_abs_beat is None:
            return False
        if self._drop_lifecycle is not None and self._drop_lifecycle_mirror:
            drop_beat = self._drop_lifecycle.drop_anchor(sp)
        elif sp.smart_drop_crossing:
            drop_beat = (
                float(sp.active_drop_beat)
                if sp.active_drop_beat is not None
                else max(ctx.abs_beat, 0.0)
            )
        else:
            drop_beat = None
        if drop_beat is None:
            return False
        return not self._laser_runway_ok(ctx.anlz_buildups, drop_beat)

    def reset_runtime_state(self, reason: str) -> None:
        del reason  # accepted for call-site symmetry / logging only
        if self._drop_lifecycle is not None:
            self._drop_lifecycle.reset()
        self._reset_smart_observation_state()

    def _decide(self, ctx: LaserContext, *, now: float) -> LaserSceneDecision:
        """Priority-ordered scene selection. Returns a LaserSceneDecision."""
        self._apply_pending_personality(ctx)

        # Priority 1: Emergency blackout (latched; bypasses all other gates).
        if self._emergency:
            return LaserSceneDecision(
                scene=self._emergency_scene,
                reason="emergency",
                priority=1,
                source="emergency",
                role="emergency",
            )

        # Priority 2: Manual override (TTL-bounded).
        if self._manual_override_scene is not None:
            if now <= self._manual_override_expires_at:
                return LaserSceneDecision(
                    scene=self._manual_override_scene,
                    reason="manual_override",
                    priority=2,
                    source="manual",
                    role="manual",
                )
            # TTL expired — clear it and fall through.
            self.clear_manual_override()

        # Priority 3: Not playing -> idle/no output.
        if not ctx.playing:
            self._last_phrase_number = None
            self._reset_smart_observation_state()
            return LaserSceneDecision(
                scene="",
                reason="not_playing",
                priority=3,
                source="policy",
                role="idle",
            )

        # Priority 4: No loaded active track -> idle/no output.
        if not ctx.active_track_loaded:
            self._last_phrase_number = None
            self._reset_smart_observation_state()
            return LaserSceneDecision(
                scene="",
                reason="idle_no_track",
                priority=4,
                source="policy",
                role="idle",
            )

        # Priority 5: Stale position -> idle/no output.
        if ctx.position_stale:
            self._last_phrase_number = None
            self._reset_smart_observation_state()
            return LaserSceneDecision(
                scene="",
                reason="position_stale",
                priority=5,
                source="policy",
                role="idle",
            )

        # Priority 6: scripted mode -> idle/no output.
        if self._is_scripted_context(ctx):
            self._last_phrase_number = None
            self._reset_smart_observation_state()
            return LaserSceneDecision(
                scene="",
                reason="scripted",
                priority=6,
                source="policy",
                role="idle",
            )

        # Priority 7: autoloop must be fully ready before automatic scenes.
        if not ctx.autoloop_ready:
            self._last_phrase_number = None
            self._reset_smart_observation_state()
            return LaserSceneDecision(
                scene="",
                reason="autoloop_not_ready",
                priority=7,
                source="policy",
                role="idle",
            )

        abs_beat = max(ctx.abs_beat, 0.0)
        phrase_number = int(abs_beat // self._phrase_interval_beats)
        effective_phrase_scene = self._effective_phrase_scene()
        first_playing_tick = self._last_phrase_number is None
        phrase_changed = False if first_playing_tick else phrase_number != self._last_phrase_number
        self._last_phrase_number = phrase_number

        previous_abs_beat = self._last_smart_abs_beat
        sp = ctx.smart_phrasing
        if sp is None:
            sp = SmartPhrasingState(
                current_phrase_label="other",
                current_phrase_is_up=False,
                current_phrase_is_chorus=False,
                current_phrase_is_low=False,
                next_smart_drop_beat=None,
                beats_to_next_drop=None,
                smart_drop_window_active=False,
                smart_drop_crossing=False,
                smart_drop_preclear_requested=False,
                smart_drop_rearm_requested=False,
                smart_post_drop_active=False,
                active_drop_beat=None,
                smart_buildup_active=False,
                smart_breakdown_active=False,
                breakdown_start_crossing=False,
                breakdown_end_crossing=False,
                smart_breakdown_clear_requested=False,
                smart_breakdown_restore_requested=False,
                transition_mask_should_arm=False,
                transition_mask_should_clear=False,
                transition_window_active=False,
                phrase_anchor_requested=False,
                phrase_anchor_preclear_requested=False,
                phrase_anchor_rearm_requested=False,
                phrase_anchor_target_beat=None,
                reason="compat",
                breakdown_restore_beat=None,
            )

        # Priority 8: Existing Smart Breakdown observation.
        breakdown_active = sp.smart_breakdown_active
        if breakdown_active and self._breakdown_scene:
            self._last_smart_abs_beat = abs_beat
            return LaserSceneDecision(
                scene=self._breakdown_scene,
                reason="breakdown_active",
                priority=8,
                source="policy",
                role="breakdown",
            )

        # Priority 9 + 10: gated drop lifecycle (mirror) OR the original ungated path.
        drop_lifecycle_mirror_on = self._drop_lifecycle_mirror
        # Part I laser runway gate: a NEW drop crossing whose beat has no bridge-
        # defined buildup marker strictly before it earns no laser drop impact.
        # Skipping the drop region here means the lifecycle never arms, so no fresh
        # drop_crossing fires and the laser falls through to the buildup / phrase-
        # default branches below. The drop / post_drop ROLE can still surface on
        # later ticks from smart-phrasing state (post-drop window), but with the
        # lifecycle unarmed nothing escalates to a new drop scene — those cycle
        # decisions only re-fire the already-held scene on an autoloop tick.
        # Fail-open when the track has no buildup markers at all. LED drop looks are
        # unaffected — this is the laser director only.
        if self._laser_drop_runway_suppressed(ctx, sp, previous_abs_beat):
            in_post_drop_hold = False
        elif self._drop_lifecycle is not None and drop_lifecycle_mirror_on:
            res = self._drop_lifecycle.resolve(sp, mutate=True)  # full LED drop region, one call
            # Preserve today's priority-9 guards (:433): do NOT emit the immediate at-anchor
            # drop_crossing on the first smart tick after a reset (previous_abs_beat is None) or
            # with an unconfigured drop scene. resolve() may still have armed the lifecycle this
            # tick — fine: the impact then surfaces as res.role == "drop" -> drop_cycle below,
            # which fires no MIDI at a blackout-mode crossing (autoloop_tick_just_fired is False
            # there), matching today's no-fire.
            if res.armed_this_tick and previous_abs_beat is not None and self._drop_scene:
                # ALLOWED impact START -> reason="drop_crossing": executor fires immediately AND
                # resolves the Smart Drop blackout, byte-identical to today for allowed crossings
                # (A4). res.armed_this_tick is True only when impact_allowed (the GATE) — an
                # ungated smart_drop_crossing in groove/buildup no longer fires a drop (A3 fix).
                self._post_drop_start_abs_beat = abs_beat
                self._last_smart_abs_beat = abs_beat
                return LaserSceneDecision(
                    scene=self._drop_scene, reason="drop_crossing",
                    priority=9, source="policy", role="drop",
                )
            if res.role == "drop":  # sustained inside the window (or guarded-out first tick)
                self._last_smart_abs_beat = abs_beat
                return LaserSceneDecision(
                    scene=self._drop_scene, reason="drop_cycle",
                    priority=10, source="policy", role="drop",
                )
            if res.role == "post_drop":
                self._last_smart_abs_beat = abs_beat
                if self._has_usable_cyclable_post_drop():
                    return LaserSceneDecision(
                        scene=self._post_drop_scene or self._drop_scene,
                        reason="post_drop_cycle",
                        priority=10, source="policy", role="post_drop",
                    )
                return LaserSceneDecision(  # no usable post_drop -> cycle drops, never dark
                    scene=self._drop_scene, reason="drop_cycle",
                    priority=10, source="policy", role="drop",
                )
            # res.role == "none": the resolver owns the drop/post_drop window, so we are NOT in a
            # post-drop hold. The preserved Priority-11 buildup gate (below) reads this local.
            in_post_drop_hold = False
        else:
            # Flag OFF (or no lifecycle): the ORIGINAL Priority-9 + Priority-10 code, VERBATIM.
            # Priority 9: Drop crossing (once per target beat).
            if previous_abs_beat is not None and self._drop_scene:
                if sp.smart_drop_crossing:
                    self._pending_drop_crossing_beat = None
                    self._drop_rearm_edge_seen_for_pending = False
                    self._post_drop_start_abs_beat = abs_beat
                    self._last_smart_abs_beat = abs_beat
                    return LaserSceneDecision(
                        scene=self._drop_scene,
                        reason="drop_crossing",
                        priority=9,
                        source="policy",
                        role="drop",
                    )

            # Priority 10: Hold after the drop.
            in_post_drop_hold = (
                self._post_drop_hold_beats > 0
                and self._post_drop_start_abs_beat >= 0.0
                and (abs_beat - self._post_drop_start_abs_beat) < self._post_drop_hold_beats
            )
            if in_post_drop_hold:
                if self._drop_style == "emphasized_drop":
                    if self._post_drop_scene:
                        self._last_smart_abs_beat = abs_beat
                        return LaserSceneDecision(
                            scene=self._post_drop_scene,
                            reason="post_drop_hold",
                            priority=10,
                            source="policy",
                            role="post_drop",
                        )
                elif self._drop_scene:
                    # drop_mode: hold the rotated drop look itself for the post-drop
                    # window; there is no separate post-drop scene. The executor keeps
                    # the already-fired (rotated) drop scene latched via role-unchanged
                    # + same-scene skip, so this decision MUST NOT re-fire MIDI — the
                    # reason is deliberately not "drop_crossing".
                    self._last_smart_abs_beat = abs_beat
                    return LaserSceneDecision(
                        scene=self._drop_scene,
                        reason="drop_hold",
                        priority=10,
                        source="policy",
                        role="drop",
                    )
        # Both branches above have either returned or set `in_post_drop_hold`. Execution continues
        # into the UNCHANGED Priority-11 buildup window + _decide_phrase_default (current :479+).

        # Priority 11: Smart Drop countdown buildup window.
        beats_to_next_drop = sp.beats_to_next_drop
        if beats_to_next_drop is None:
            beats_to_next_drop = float('inf')

        current_phrase_is_up = sp.current_phrase_is_up
        current_phrase_is_chorus = sp.current_phrase_is_chorus
        in_buildup_window = (
            bool(self._buildup_scene)
            and self._buildup_lookahead_beats > 0
            and 0 < beats_to_next_drop <= self._buildup_lookahead_beats
        )

        if in_buildup_window and (
            not in_post_drop_hold
            and current_phrase_is_up
            and not current_phrase_is_chorus
        ):
            self._log_buildup_gate(
                decision="allowed",
                reason="up_phrase",
                abs_beat=abs_beat,
                beats_to_next_drop=beats_to_next_drop,
                current_phrase_is_up=current_phrase_is_up,
                current_phrase_is_chorus=current_phrase_is_chorus,
                in_post_drop_hold=in_post_drop_hold,
            )
            self._last_smart_abs_beat = abs_beat
            return LaserSceneDecision(
                scene=self._buildup_scene,
                reason="buildup_to_drop_window",
                priority=11,
                source="policy",
                role="buildup",
            )
        if in_buildup_window:
            if in_post_drop_hold:
                buildup_gate_reason = "post_drop_hold"
            elif current_phrase_is_chorus:
                buildup_gate_reason = "chorus"
            else:
                buildup_gate_reason = "not_up"
            self._log_buildup_gate(
                decision="blocked",
                reason=buildup_gate_reason,
                abs_beat=abs_beat,
                beats_to_next_drop=beats_to_next_drop,
                current_phrase_is_up=current_phrase_is_up,
                current_phrase_is_chorus=current_phrase_is_chorus,
                in_post_drop_hold=in_post_drop_hold,
            )

        self._last_smart_abs_beat = abs_beat
        if (
            self._post_drop_start_abs_beat >= 0.0
            and self._post_drop_hold_beats <= 0
        ):
            self._post_drop_start_abs_beat = -1.0

        return self._decide_phrase_default(
            ctx=ctx,
            first_playing_tick=first_playing_tick,
            phrase_changed=phrase_changed,
            effective_phrase_scene=effective_phrase_scene,
        )

    def _log_buildup_gate(
        self,
        *,
        decision: str,
        reason: str,
        abs_beat: float,
        beats_to_next_drop: float,
        current_phrase_is_up: bool,
        current_phrase_is_chorus: bool,
        in_post_drop_hold: bool,
    ) -> None:
        beat_bucket = int(max(abs_beat, 0.0))
        key = (
            beat_bucket,
            decision,
            reason,
            bool(current_phrase_is_up),
            bool(current_phrase_is_chorus),
            bool(in_post_drop_hold),
        )
        if key == self._last_buildup_gate_log_key:
            return
        self._last_buildup_gate_log_key = key
        log.info(
            "[LASER] buildup-gate  decision=%s  reason=%s  beat=%.2f  "
            "drop_in=%.2f  lookahead=%d  up=%s  chorus=%s  post_hold=%s  scene=%s",
            decision,
            reason,
            abs_beat,
            beats_to_next_drop,
            self._buildup_lookahead_beats,
            current_phrase_is_up,
            current_phrase_is_chorus,
            in_post_drop_hold,
            self._buildup_scene,
        )

    def _apply_pending_personality(self, ctx: LaserContext) -> None:
        pending = self._pending_personality
        if pending is None:
            return
        if self._is_scripted_context(ctx):
            return
        if not self._pending_personality_can_apply(ctx):
            return

        name, config = pending
        self._pending_personality = None
        if self._personality_apply_callback is not None:
            self._personality_apply_callback(name, config)
        else:
            self.set_personality(name)
            self.set_personality_config(config)
        bridge_log.perf(
            "laser.personality",
            "personality active=%s",
            name,
            deck=ctx.active_deck,
            beat=ctx.abs_beat,
            data={"personality": name},
        )

    def _pending_personality_can_apply(self, ctx: LaserContext) -> bool:
        if not ctx.playing or not ctx.active_track_loaded or ctx.lighting_mode == "idle":
            return True
        if ctx.autoloop_tick_just_fired:
            return True
        # Outgoing personality owns boundary timing until it releases.
        # New personality's phrase_interval_beats takes effect on next phrase.
        interval = max(1, self._phrase_interval_beats)
        abs_beat = max(ctx.abs_beat, 0.0)
        nearest_boundary = round(abs_beat / interval) * interval
        return abs(abs_beat - nearest_boundary) < 0.01

    def _decide_phrase_default(
        self,
        *,
        ctx: LaserContext,
        first_playing_tick: bool,
        phrase_changed: bool,
        effective_phrase_scene: str,
    ) -> LaserSceneDecision:
        if first_playing_tick:
            self._phrase_trigger_pending = False
            return self._gate_normal_change(
                ctx=ctx,
                candidate_scene=self._default_scene,
                candidate_reason="default_init",
                priority=10,
            )

        if phrase_changed:
            self._phrase_trigger_pending = True

        sp = ctx.smart_phrasing
        if sp is not None and (sp.phrase_anchor_requested or sp.breakdown_end_crossing):
            # Marker crossings and breakdown restores are phrase boundaries for
            # the marker-relative re-fire model; arm the pending latch so the
            # same-tick autoloop_tick_just_fired emits a phrase_boundary fire.
            self._phrase_trigger_pending = True

        if ctx.autoloop_tick_just_fired:
            self._phrase_trigger_pending = False
            return self._gate_normal_change(
                ctx=ctx,
                candidate_scene=effective_phrase_scene,
                candidate_reason="phrase_boundary",
                priority=10,
            )

        if self._phrase_trigger_pending and self._is_normal_auto_scene(self._current_scene):
            return LaserSceneDecision(
                scene=self._current_scene,
                reason="phrase_hold_pending",
                priority=10,
                source="policy",
                role="phrase",
            )

        if self._normal_changes_only_on_phrase_boundary:
            if self._is_normal_auto_scene(self._current_scene):
                return LaserSceneDecision(
                    scene=self._current_scene,
                    reason="phrase_hold",
                    priority=10,
                    source="policy",
                    role="phrase",
                )
            return self._gate_normal_change(
                ctx=ctx,
                candidate_scene=self._default_scene,
                candidate_reason="default",
                priority=10,
            )

        return self._gate_normal_change(
            ctx=ctx,
            candidate_scene=self._default_scene,
            candidate_reason="default",
            priority=10,
        )

    def _is_scripted_context(self, ctx: LaserContext) -> bool:
        return ctx.scripted_id > 0 or ctx.lighting_mode == "scripted"

    def _reset_smart_observation_state(self) -> None:
        self._pending_drop_crossing_beat = None
        self._drop_rearm_edge_seen_for_pending = False
        self._post_drop_start_abs_beat = -1.0
        self._last_smart_abs_beat = None
        self._smart_drop_blackout_active = False
        self._phrase_trigger_pending = False
        self._last_buildup_gate_log_key = None

    def _effective_phrase_scene(self) -> str:
        return self._phrase_scene or self._default_scene

    def _is_normal_auto_scene(self, scene: str) -> bool:
        return scene in (self._default_scene, self._effective_phrase_scene())

    def _gate_normal_change(
        self,
        *,
        ctx: LaserContext,
        candidate_scene: str,
        candidate_reason: str,
        priority: int,
    ) -> LaserSceneDecision:
        if (
            candidate_scene != self._current_scene
            and self._is_normal_auto_scene(candidate_scene)
            and self._is_normal_auto_scene(self._current_scene)
            and self._minimum_scene_hold_beats > 0
        ):
            held_for_beats = max(ctx.abs_beat, 0.0) - self._last_scene_change_abs_beat
            if held_for_beats < self._minimum_scene_hold_beats:
                return LaserSceneDecision(
                    scene=self._current_scene,
                    reason="hold_minimum_scene",
                    priority=priority,
                    source="policy",
                    role=self._role_for_reason("hold_minimum_scene"),
                )

        return LaserSceneDecision(
            scene=candidate_scene,
            reason=candidate_reason,
            priority=priority,
            source="policy",
            role=self._role_for_reason(candidate_reason),
        )

    def _role_for_reason(self, reason: str) -> str:
        if reason == "emergency":
            return "emergency"
        if reason == "manual_override":
            return "manual"
        if reason in (
            "not_playing",
            "idle_no_track",
            "position_stale",
            "scripted",
            "autoloop_not_ready",
        ):
            return "idle"
        if reason == "breakdown_active":
            return "breakdown"
        if reason in ("drop_crossing", "drop_hold"):
            return "drop"
        if reason == "post_drop_hold":
            return "post_drop"
        if reason == "buildup_to_drop_window":
            return "buildup"
        return "phrase"

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a status dict. Safe to call from any thread (StatusWriter).

        Each field is read atomically (CPython), but the returned dict is a
        loose snapshot: values may reflect a mix of states across one tick
        boundary. This is acceptable for operator display.
        """
        return {
            "available": True,
            "enabled": self._enabled,
            "dry_run": self._dry_run,
            "current_scene": self._current_scene,
            "last_reason": self._last_reason,
            "manual_override": self._manual_override_scene,
            "emergency": self._emergency,
            "last_error": self._last_error,
            "personality": self._personality,
            "pending_personality": (
                self._pending_personality[0] if self._pending_personality else None
            ),
            "phrase_scene": self._phrase_scene,
            "phrase_interval_beats": self._phrase_interval_beats,
            "minimum_scene_hold_beats": self._minimum_scene_hold_beats,
            "post_drop_hold_beats": self._post_drop_hold_beats,
            "drop_style": self._drop_style,
            "normal_changes_only_on_phrase_boundary": self._normal_changes_only_on_phrase_boundary,
            "breakdown_scene": self._breakdown_scene,
            "buildup_scene": self._buildup_scene,
            "drop_scene": self._drop_scene,
            "post_drop_scene": self._post_drop_scene,
            "buildup_lookahead_beats": self._buildup_lookahead_beats,
            "pending_drop_crossing_beat": self._pending_drop_crossing_beat,
            "drop_rearm_edge_seen_for_pending": self._drop_rearm_edge_seen_for_pending,
            "smart_drop_blackout_active": self._smart_drop_blackout_active,
            "phrase_trigger_pending": self._phrase_trigger_pending,
            "last_trigger_abs_beat": self._last_trigger_abs_beat,
            "recent_decisions": self._decision_log.recent_as_dicts(32),
        }
