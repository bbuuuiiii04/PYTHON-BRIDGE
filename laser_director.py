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
from typing import Literal, Optional

from .laser_decision_log import LaserDecision, LaserDecisionLog
from .laser_models import LaserContext, LaserPersonality, LaserSceneDecision
from .smart_phrasing import SmartPhrasingState

log = logging.getLogger("laser_director")

# These are example scene names taken from the operator's early mapping notes
# (docs/laser_director_midi_mapping_workflow.md). They are constructor defaults
# only — any arbitrary string is valid. A future config loader must supply its
# own values rather than relying on these constants.
_DEFAULT_SAFE_SCENE = "safe_static"
_DEFAULT_DEFAULT_SCENE = "house_phrase_1"
_DEFAULT_EMERGENCY_SCENE = "emergency_blackout"


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
        pre_drop_scene: str = "",
        drop_scene: str = "",
        post_drop_scene: str = "",
        buildup_lookahead_beats: int = 32,
        buildup_approach_beats: int = 8,
        buildup_hold_beats: int = 8,
        pre_drop_lookahead_beats: int = 4,
        buildup_max_drop_distance_beats: int = 32,
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
        self._pre_drop_scene = pre_drop_scene
        self._drop_scene = drop_scene
        self._post_drop_scene = post_drop_scene
        self._buildup_lookahead_beats = max(0, int(buildup_lookahead_beats))
        # Deprecated/inert in active policy; retained for compatibility/status.
        self._buildup_approach_beats = max(0, int(buildup_approach_beats))
        self._buildup_hold_beats = max(0, int(buildup_hold_beats))
        self._pre_drop_lookahead_beats = max(0, int(pre_drop_lookahead_beats))
        self._buildup_max_drop_distance_beats = max(1, int(buildup_max_drop_distance_beats))

        # Mutable policy state — written only from the StateManager thread.
        self._emergency: bool = False
        self._manual_override_scene: Optional[str] = None
        self._manual_override_expires_at: float = 0.0
        self._current_scene: str = ""
        self._last_reason: str = ""
        self._last_error: str = ""
        self._personality: str = ""
        self._last_phrase_number: Optional[int] = None
        self._last_scene_change_abs_beat: float = 0.0
        self._last_trigger_abs_beat: float = 0.0
        self._pending_drop_crossing_beat: Optional[int] = None
        self._drop_rearm_edge_seen_for_pending: bool = False
        self._post_drop_start_abs_beat: float = -1.0
        self._last_smart_abs_beat: Optional[float] = None
        self._phrase_trigger_pending: bool = False
        self._smart_drop_blackout_active: bool = False
        self._decision_log = LaserDecisionLog()

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
        self._pre_drop_scene = personality.pre_drop_scene
        self._drop_scene = personality.drop_scene
        self._post_drop_scene = personality.post_drop_scene
        self._buildup_lookahead_beats = max(0, int(personality.buildup_lookahead_beats))
        # Deprecated/inert in active policy; retained for compatibility/status.
        self._buildup_approach_beats = max(0, int(personality.buildup_approach_beats))
        self._buildup_hold_beats = max(0, int(personality.buildup_hold_beats))
        self._pre_drop_lookahead_beats = max(
            0, int(personality.pre_drop_lookahead_beats)
        )

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
            log.info(
                "[LASER] scene  %s->%s  reason=%s  dry_run=%s",
                self._current_scene or "(none)",
                decision.scene,
                decision.reason,
                self._dry_run,
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

    def _decide(self, ctx: LaserContext, *, now: float) -> LaserSceneDecision:
        """Priority-ordered scene selection. Returns a LaserSceneDecision."""

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

        # Priority 10: Post-drop hold (using existing minimum_scene_hold_beats).
        if (
            self._post_drop_scene
            and self._minimum_scene_hold_beats > 0
            and self._post_drop_start_abs_beat >= 0.0
            and (abs_beat - self._post_drop_start_abs_beat) < self._minimum_scene_hold_beats
        ):
            self._last_smart_abs_beat = abs_beat
            return LaserSceneDecision(
                scene=self._post_drop_scene,
                reason="post_drop_hold",
                priority=10,
                source="policy",
                role="post_drop",
            )

        in_post_drop_hold = (
            self._post_drop_start_abs_beat >= 0.0
            and self._minimum_scene_hold_beats > 0
            and (abs_beat - self._post_drop_start_abs_beat) < self._minimum_scene_hold_beats
        )

        # Priority 11: Smart Drop countdown buildup window.
        beats_to_next_drop = sp.beats_to_next_drop
        if beats_to_next_drop is None:
            beats_to_next_drop = float('inf')

        current_phrase_is_up = sp.current_phrase_is_up
        current_phrase_is_chorus = sp.current_phrase_is_chorus

        if (
            self._buildup_scene
            and not in_post_drop_hold
            and current_phrase_is_up
            and not current_phrase_is_chorus
            and self._buildup_lookahead_beats > 0
            and 0 < beats_to_next_drop <= self._buildup_lookahead_beats
        ):
            self._last_smart_abs_beat = abs_beat
            return LaserSceneDecision(
                scene=self._buildup_scene,
                reason="buildup_to_drop_window",
                priority=11,
                source="policy",
                role="buildup",
            )

        self._last_smart_abs_beat = abs_beat
        if (
            self._post_drop_start_abs_beat >= 0.0
            and self._minimum_scene_hold_beats <= 0
        ):
            self._post_drop_start_abs_beat = -1.0

        return self._decide_phrase_default(
            ctx=ctx,
            first_playing_tick=first_playing_tick,
            phrase_changed=phrase_changed,
            effective_phrase_scene=effective_phrase_scene,
        )

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

        if self._phrase_trigger_pending and ctx.autoloop_tick_just_fired:
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
        if reason == "drop_crossing":
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
            "phrase_scene": self._phrase_scene,
            "phrase_interval_beats": self._phrase_interval_beats,
            "minimum_scene_hold_beats": self._minimum_scene_hold_beats,
            "normal_changes_only_on_phrase_boundary": self._normal_changes_only_on_phrase_boundary,
            "breakdown_scene": self._breakdown_scene,
            "buildup_scene": self._buildup_scene,
            "pre_drop_scene": self._pre_drop_scene,
            "drop_scene": self._drop_scene,
            "post_drop_scene": self._post_drop_scene,
            "buildup_lookahead_beats": self._buildup_lookahead_beats,
            "buildup_approach_beats": self._buildup_approach_beats,
            "buildup_hold_beats": self._buildup_hold_beats,
            "buildup_max_drop_distance_beats": self._buildup_max_drop_distance_beats,
            "pre_drop_lookahead_beats": self._pre_drop_lookahead_beats,
            "pending_drop_crossing_beat": self._pending_drop_crossing_beat,
            "drop_rearm_edge_seen_for_pending": self._drop_rearm_edge_seen_for_pending,
            "smart_drop_blackout_active": self._smart_drop_blackout_active,
            "phrase_trigger_pending": self._phrase_trigger_pending,
            "last_trigger_abs_beat": self._last_trigger_abs_beat,
            "recent_decisions": self._decision_log.recent_as_dicts(32),
        }
