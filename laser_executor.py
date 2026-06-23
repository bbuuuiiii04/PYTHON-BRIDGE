"""LaserSceneExecutor — resolves policy decisions into MIDI triggers.

This module intentionally keeps policy selection in LaserDirector while owning:
- role bank rotation (deterministic round-robin),
- scene lookup in validated LaserConfig,
- execution gates for live-safe triggering, and
- delegation to the injected LaserOutputBackend.trigger().
"""
from __future__ import annotations

from dataclasses import replace
import logging
import random
import threading
import time
from typing import Optional

from .laser_config import LaserConfig
from .laser_models import LaserContext, LaserPersonality, LaserSceneDecision
from .laser_output_backend import LaserOutputBackend

log = logging.getLogger("laser_executor")

_AUTO_ROLES = ("phrase", "buildup", "drop", "post_drop", "breakdown")
_PHRASE_TRIGGER_REASONS = frozenset({"default_init", "phrase_boundary"})
_MIN_HOLD_MS = 10
_MAX_HOLD_MS = 30000
_DROP_CROSSING_MIN_PULSE_MS = 120


class LaserSceneExecutor:
    """Non-blocking decision executor for Laser Director."""

    def __init__(
        self,
        *,
        config: LaserConfig,
        backend: LaserOutputBackend,
        personality: Optional[LaserPersonality],
        rng: Optional[random.Random] = None,
        randomize_cursors: bool = True,
    ) -> None:
        self._config = config
        self._backend = backend
        self._personality = personality
        self._rng = rng if rng is not None else random.Random()
        self._randomize_cursors = bool(randomize_cursors)
        self._lock = threading.Lock()
        self._last_role = "idle"
        self._last_triggered_scene = ""
        self._last_reason = ""
        self._last_error = ""
        self._last_trigger_at = 0.0
        self._triggered_count = 0
        self._gated_count = 0
        self._missing_scene_count = 0
        self._same_scene_skip_count = 0
        self._role_bank_shuffle: dict[str, tuple[str, ...]] = {}
        self._role_cursors = self._seed_role_cursors()
        self._role_active_scene = {role: "" for role in _AUTO_ROLES}
        self._role_last_trigger_beat = {role: -1.0 for role in _AUTO_ROLES}
        self._blackout_pending_for_drop_window = False
        # Named blackout-mask holders (breakdown, master_switch). The physical
        # MIDI note is shared with the Smart Drop blackout; note_off is only
        # sent when BOTH the drop-window latch and this set are clear.
        self._mask_owners: set[str] = set()
        self._role_bag: dict[str, tuple[str, ...]] = {}

    def set_personality(self, personality: Optional[LaserPersonality]) -> None:
        """Switch executor personality and reset role-bank execution state."""
        with self._lock:
            self._personality = personality
        self.reset_runtime_state(reason="set_personality", reset_cursors=True)

    def smart_drop_blackout_enabled(self) -> bool:
        """Return whether Smart Drop should use blackout-mask timing."""
        return str(getattr(self._config, "smart_drop_mode", "blackout_mask")) == "blackout_mask"

    def clear_pending_blackout(self, *, reason: str = "smart_drop_reset") -> None:
        """Clear a pending Smart Drop blackout window, if any."""
        self._release_all_masks()
        self._resolve_pending_blackout(reason=reason)

    def reset_runtime_state(self, *, reason: str = "runtime_reset", reset_cursors: bool = False) -> None:
        """Reset role cooldown/bank state across track/deck lifecycle changes."""
        with self._lock:
            self._last_role = "idle"
            self._last_reason = ""
            self._last_triggered_scene = ""
            self._last_error = ""
            if reset_cursors:
                self._role_cursors = self._seed_role_cursors()
            self._reshuffle_phrase_bank_locked()
            self._role_active_scene = {role: "" for role in _AUTO_ROLES}
            self._role_bag = {}
            self._role_last_trigger_beat = {role: -1.0 for role in _AUTO_ROLES}
        self.clear_pending_blackout(reason=reason)

    def on_tick(self, ctx: LaserContext) -> None:
        """Consume per-tick SmartPhrasing cleanup intents before decision output."""
        sp = ctx.smart_phrasing
        if sp is None:
            return
        if sp.transition_mask_should_clear:
            self._resolve_pending_blackout(reason="smart_phrasing_transition_mask_clear")

    def on_decision(self, decision: Optional[LaserSceneDecision], ctx: LaserContext) -> None:
        """Consume one decision and trigger MIDI when all gates pass."""
        if decision is None:
            return
        is_drop_crossing = decision.reason == "drop_crossing"

        role = decision.role or "idle"
        with self._lock:
            previous_role = self._last_role
            role_changed = role != previous_role
            if role_changed:
                if previous_role in self._role_active_scene:
                    self._role_active_scene[previous_role] = ""
                self._last_role = role
            self._last_reason = decision.reason

        should_arm_blackout = bool(
            (ctx.smart_drop_blackout_arm or ctx.smart_phrasing_blackout_arm)
            and role in _AUTO_ROLES
        )

        if role == "idle" or not decision.scene:
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_idle")
            if should_arm_blackout:
                log.debug("[LX] blackout skipped: decision has no scene (role=%s, scene=%s)", role, decision.scene)
            return

        if role in _AUTO_ROLES and not self._passes_automatic_gates(ctx):
            self._record_gate("auto_gate_blocked")
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_auto_gate_blocked")
            if should_arm_blackout:
                log.debug("[LX] blackout skipped: auto_gate_blocked (playing=%s, track_loaded=%s, stale=%s, mode=%s, scripted=%s, autoloop_ready=%s)", ctx.playing, ctx.active_track_loaded, ctx.position_stale, ctx.lighting_mode, ctx.scripted_id, ctx.autoloop_ready)
            return

        # Blackout arming is independent of scene selection and scene policy
        # gates. It must fire on every valid auto-tick where the arm signal is
        # raised, even when _select_scene declines to trigger scene MIDI on
        # this tick (e.g., role="phrase" outside a phrase_boundary, which is
        # the typical state for mini-drops <32 beats apart). Missing scene
        # mapping is still respected by checking the policy-supplied scene
        # against the configured scene catalog.
        if should_arm_blackout:
            if decision.scene in self._config.scenes:
                log.debug("[LX] blackout arming: role=%s, reason=%s", role, decision.reason)
                self.trigger_blackout_on(ctx)
            else:
                log.debug("[LX] blackout skipped: missing scene mapping for '%s'", decision.scene)

        cursor_before, active_before = self._role_state_snapshot(role)
        selected_scene = self._select_scene(decision, ctx, role_changed)
        if not selected_scene:
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_no_scene")
            return

        scene_def = self._config.scenes.get(selected_scene)
        if scene_def is None:
            with self._lock:
                self._missing_scene_count += 1
                self._gated_count += 1
                self._last_error = f"missing_scene_mapping:{selected_scene}"
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_missing_scene_mapping")
            return

        allow_high_impact = bool(
            self._personality.allow_high_impact if self._personality is not None else False
        )
        if role != "emergency" and scene_def.safety_class == "high_impact" and not allow_high_impact:
            self._record_gate("high_impact_blocked")
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_high_impact_blocked")
            return

        refire_roles = ("phrase", "buildup", "breakdown")
        cycling = decision.reason in ("drop_cycle", "post_drop_cycle")
        with self._lock:
            last_role_trigger_beat = float(self._role_last_trigger_beat.get(role, -1.0))
            refire_allowed = (
                ctx.autoloop_tick_just_fired
                and (role in refire_roles or (cycling and role in ("drop", "post_drop")))
                and scene_def.scene_type == "autoloop"
                and (last_role_trigger_beat < 0.0 or float(ctx.abs_beat) > last_role_trigger_beat)
            )
            same_scene_candidate = (
                role not in ("manual", "emergency")
                and not is_drop_crossing
                and selected_scene == self._last_triggered_scene
            )
            same_scene_refire = same_scene_candidate and refire_allowed

        if self._is_role_cooldown_blocked(
            role,
            scene_def.cooldown_beats,
            ctx.abs_beat,
            role_changed=role_changed,
            previous_role=previous_role,
        ) and not same_scene_refire:
            self._restore_role_state(role, cursor_before, active_before)
            self._record_gate("role_cooldown_blocked")
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_role_cooldown_blocked")
            return

        same_scene_skip = False
        with self._lock:
            if (
                same_scene_candidate
                and not refire_allowed
            ):
                self._same_scene_skip_count += 1
                same_scene_skip = True
        if same_scene_skip:
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_same_scene_skip")
            return
        if same_scene_refire:
            log.info(
                "[LX] same-scene-refire  role=%s  scene=%s  reason=%s  beat=%.2f",
                role,
                selected_scene,
                decision.reason,
                ctx.abs_beat,
            )

        priority = self._priority_for_role(role)
        midi_message = self._materialize_midi(
            scene_def.midi,
            ctx,
            reason=decision.reason,
            scene_name=selected_scene,
        )
        if not self._backend.trigger(midi_message, priority=priority):
            self._record_gate("midi_trigger_rejected")
            if is_drop_crossing:
                self._resolve_pending_blackout(reason="drop_crossing_midi_trigger_rejected")
            return

        if is_drop_crossing:
            self._resolve_pending_blackout(reason="drop_crossing_success")

        with self._lock:
            self._triggered_count += 1
            self._last_triggered_scene = selected_scene
            self._last_trigger_at = time.monotonic()
            self._last_error = ""
            if role in self._role_last_trigger_beat:
                self._role_last_trigger_beat[role] = float(ctx.abs_beat)
            fired_cursor = self._role_cursors.get(role)

        # Observability: the scene the executor ACTUALLY fired (after bank
        # rotation), which the director's decision log cannot show. This is the
        # signal to confirm drop-bank rotation on the rig.
        log.info(
            "[LX] fired  role=%s  scene=%s  note=%s  reason=%s  cursor=%s",
            role,
            selected_scene,
            getattr(scene_def.midi, "note", None),
            decision.reason,
            fired_cursor,
        )

    def trigger_blackout_on(self, ctx: LaserContext) -> None:
        """Send manual blackout-on MIDI command for Smart Drop pre-window."""
        del ctx  # context reserved for future diagnostics.
        if not self.smart_drop_blackout_enabled():
            log.debug("[LX] blackout_on skipped: smart_drop_blackout not enabled")
            return
        with self._lock:
            if self._blackout_pending_for_drop_window:
                log.debug("[LX] blackout_on skipped: already pending for drop window")
                return
        msg = self._config.manual_blackout_on
        if msg is None:
            log.debug("[LX] blackout_on skipped: manual_blackout_on not configured")
            return
        if self._backend.trigger(msg, priority="high"):
            with self._lock:
                self._blackout_pending_for_drop_window = True
            log.info("[LX] blackout_on sent  note=%s  channel=%s", msg.note, msg.channel)
            return
        self._record_gate("manual_blackout_on_rejected")
        log.warning("[LX] blackout_on rejected by midi_output")

    def _resolve_pending_blackout(self, *, reason: str) -> None:
        """Send blackout-off exactly once for each armed blackout window."""
        with self._lock:
            pending = self._blackout_pending_for_drop_window
            if pending:
                self._blackout_pending_for_drop_window = False
            owners_remain = bool(self._mask_owners)
        if not pending or owners_remain:
            return
        msg = self._config.manual_blackout_off
        if msg is None:
            return
        if not self._backend.trigger(msg, priority="high"):
            self._record_gate("manual_blackout_off_rejected")

    def hold_blackout_mask(self, owner: str) -> None:
        """Hold the manual blackout note on behalf of *owner* (refcounted by name)."""
        if not self.smart_drop_blackout_enabled():
            return
        msg = self._config.manual_blackout_on
        if msg is None:
            return
        with self._lock:
            already_dark = bool(self._mask_owners) or self._blackout_pending_for_drop_window
            self._mask_owners.add(owner)
        if already_dark:
            return
        if self._backend.trigger(msg, priority="high"):
            log.info("[LX] mask_on  owner=%s  note=%s", owner, msg.note)
            return
        with self._lock:
            self._mask_owners.discard(owner)
        self._record_gate("manual_blackout_on_rejected")

    def release_blackout_mask(self, owner: str) -> None:
        """Release *owner*'s hold; sends note_off only when nothing else holds it."""
        with self._lock:
            if owner not in self._mask_owners:
                return
            self._mask_owners.discard(owner)
            still_dark = bool(self._mask_owners) or self._blackout_pending_for_drop_window
        log.info("[LX] mask_off  owner=%s  still_dark=%s", owner, still_dark)
        if still_dark:
            return
        msg = self._config.manual_blackout_off
        if msg is None:
            return
        if not self._backend.trigger(msg, priority="high"):
            self._record_gate("manual_blackout_off_rejected")

    def _release_all_masks(self) -> None:
        with self._lock:
            owners = tuple(self._mask_owners)
        for owner in owners:
            self.release_blackout_mask(owner)

    def status(self) -> dict:
        with self._lock:
            role_cursors = dict(self._role_cursors)
            active_scenes = dict(self._role_active_scene)
            last_trigger_beats = dict(self._role_last_trigger_beat)
            return {
                "dry_run": self._config.dry_run,
                "smart_drop_mode": str(getattr(self._config, "smart_drop_mode", "blackout_mask")),
                "manual_blackout_commands_configured": (
                    self._config.manual_blackout_on is not None
                    and self._config.manual_blackout_off is not None
                ),
                "last_role": self._last_role,
                "last_reason": self._last_reason,
                "last_scene": self._last_triggered_scene,
                "last_trigger_at": self._last_trigger_at,
                "last_error": self._last_error,
                "triggered_count": self._triggered_count,
                "gated_count": self._gated_count,
                "missing_scene_count": self._missing_scene_count,
                "same_scene_skip_count": self._same_scene_skip_count,
                "blackout_pending_for_drop_window": self._blackout_pending_for_drop_window,
                "blackout_mask_owners": sorted(self._mask_owners),
                "role_cursors": role_cursors,
                "role_active_scenes": active_scenes,
                "role_last_trigger_beat": last_trigger_beats,
                "midi": self._backend.status(),
            }

    def _select_scene(
        self,
        decision: LaserSceneDecision,
        ctx: LaserContext,
        role_changed: bool,
    ) -> str:
        role = decision.role
        if role in ("manual", "emergency"):
            return decision.scene
        if role not in _AUTO_ROLES:
            return decision.scene

        cycling = decision.reason in ("drop_cycle", "post_drop_cycle")
        mirror_on = bool(
            self._personality is not None
            and getattr(self._personality, "drop_lifecycle_mirror", False)
        )
        flag_on_drop_impact = (
            mirror_on and role == "drop" and decision.reason == "drop_crossing"
        )

        with self._lock:
            if role == "phrase":
                if decision.reason not in _PHRASE_TRIGGER_REASONS:
                    return ""
                # Phrase/default should only trigger on real autoloop phrase edges.
                if decision.reason == "phrase_boundary" and not ctx.autoloop_tick_just_fired:
                    return ""
                return self._choose_bank_scene_locked(role=role, fallback_scene=decision.scene)

            if role in ("drop", "post_drop") and cycling:
                # Cycle ticks fire ONLY on an autoloop edge; empty usable set -> no-op (hold).
                if not ctx.autoloop_tick_just_fired:
                    return ""
                return self._next_shuffled_scene_locked(role)

            if flag_on_drop_impact:
                # At-anchor impact: shuffled when usable, else the static one-shot (A8, never dark).
                scene = self._next_shuffled_scene_locked("drop")
                if not scene:
                    scene = decision.scene
                return scene

            active_scene = self._role_active_scene.get(role, "")
            if role_changed or not active_scene:
                return self._choose_bank_scene_locked(role=role, fallback_scene=decision.scene)
            return active_scene

    def _choose_bank_scene_locked(self, *, role: str, fallback_scene: str) -> str:
        bank = self._bank_for_role(role)
        if not bank:
            bank = (fallback_scene,)
        if not bank or not bank[0]:
            self._role_active_scene[role] = ""
            return ""
        cursor = self._role_cursors.get(role, 0)
        index = cursor % len(bank)
        scene = bank[index]
        self._role_cursors[role] = cursor + 1
        self._role_active_scene[role] = scene
        return scene

    def _usable_bag_entries(self, role: str) -> list[str]:
        allow_high_impact = bool(
            self._personality.allow_high_impact if self._personality is not None else False
        )
        out: list[str] = []
        for name in self._bank_for_role(role):
            sd = self._config.scenes.get(name)
            if sd is None:
                continue
            if sd.scene_type != "autoloop":
                continue
            if sd.safety_class == "high_impact" and not allow_high_impact:
                continue
            out.append(name)
        return out

    def _next_shuffled_scene_locked(self, role: str) -> str:
        usable = self._usable_bag_entries(role)
        if not usable:
            self._role_active_scene[role] = ""
            return ""                       # caller decides: impact-fallback (4e) / cycle no-op
        cursor = self._role_cursors.get(role, 0)
        bag = self._role_bag.get(role, ())
        if cursor % len(usable) == 0 or not bag or len(bag) != len(usable):
            shuffled = list(usable)
            self._rng.shuffle(shuffled)     # reshuffle on exhaustion / bank-membership change
            bag = tuple(shuffled)
            self._role_bag[role] = bag
        scene = bag[cursor % len(bag)]
        self._role_cursors[role] = cursor + 1
        self._role_active_scene[role] = scene
        return scene

    def _seed_role_cursors(self) -> dict[str, int]:
        if not self._randomize_cursors:
            return {role: 0 for role in _AUTO_ROLES}
        cursors: dict[str, int] = {}
        for role in _AUTO_ROLES:
            bank = self._bank_for_role(role)
            cursors[role] = self._rng.randrange(len(bank)) if bank else 0
        return cursors

    def _reshuffle_phrase_bank_locked(self) -> None:
        """Re-randomize phrase-bank traversal order. Caller must hold self._lock."""
        personality = self._personality
        bank = list(personality.phrase_bank) if personality is not None else []
        if len(bank) > 1:
            self._rng.shuffle(bank)
            self._role_bank_shuffle["phrase"] = tuple(bank)
            self._role_cursors["phrase"] = 0
        else:
            self._role_bank_shuffle.pop("phrase", None)

    def _bank_for_role(self, role: str) -> tuple[str, ...]:
        personality = self._personality
        if personality is None:
            return ()
        if role == "phrase":
            shuffled = self._role_bank_shuffle.get("phrase")
            if shuffled:
                return shuffled
            return personality.phrase_bank
        if role == "buildup":
            return personality.buildup_bank
        if role == "drop":
            return personality.drop_bank
        if role == "post_drop":
            return personality.post_drop_bank
        if role == "breakdown":
            return personality.breakdown_bank
        return ()

    def _passes_automatic_gates(self, ctx: LaserContext) -> bool:
        return (
            ctx.playing
            and ctx.active_track_loaded
            and not ctx.position_stale
            and ctx.lighting_mode == "autoloop"
            and ctx.scripted_id == 0
            and ctx.autoloop_ready
        )

    def _record_gate(self, reason: str) -> None:
        with self._lock:
            self._gated_count += 1
            self._last_error = reason
        log.debug("[LX] gate-block  reason=%s", reason)

    def _is_role_cooldown_blocked(
        self,
        role: str,
        cooldown_beats: float,
        abs_beat: float,
        *,
        role_changed: bool,
        previous_role: str,
    ) -> bool:
        if role not in _AUTO_ROLES:
            return False
        # Keep the intended "UP -> DROP" path eligible even if a recent drop
        # was triggered; this is a musical transition, not spam retriggering.
        if role == "drop" and role_changed and previous_role == "buildup":
            return False
        cooldown = float(cooldown_beats)
        if cooldown <= 0:
            return False
        with self._lock:
            last_beat = float(self._role_last_trigger_beat.get(role, -1.0))
        if last_beat < 0:
            return False
        return (float(abs_beat) - last_beat) < cooldown

    def _role_state_snapshot(self, role: str) -> tuple[int, str]:
        if role not in _AUTO_ROLES:
            return (0, "")
        with self._lock:
            return (
                int(self._role_cursors.get(role, 0)),
                str(self._role_active_scene.get(role, "")),
            )

    def _restore_role_state(self, role: str, cursor: int, active_scene: str) -> None:
        if role not in _AUTO_ROLES:
            return
        with self._lock:
            self._role_cursors[role] = int(cursor)
            self._role_active_scene[role] = active_scene

    def _priority_for_role(self, role: str) -> str:
        if role in ("emergency", "manual", "drop"):
            return "high"
        return "normal"

    def _materialize_midi(self, msg, ctx: LaserContext, *, reason: str, scene_name: str = ""):
        behavior = (msg.behavior or "").strip().lower()
        if behavior == "hold_beats":
            bpm = float(ctx.bpm) if ctx.bpm else 0.0
            if bpm <= 0:
                hold_ms = _MIN_HOLD_MS
            else:
                hold_ms = int(round((60000.0 * float(msg.hold_beats)) / bpm))
            hold_ms = max(_MIN_HOLD_MS, min(_MAX_HOLD_MS, hold_ms))
            return replace(msg, behavior="hold_ms", hold_ms=hold_ms, scene_name=scene_name)
        if behavior == "pulse" and reason == "drop_crossing":
            duration_ms = int(getattr(msg, "duration_ms", 0))
            if duration_ms < _DROP_CROSSING_MIN_PULSE_MS:
                return replace(msg, duration_ms=_DROP_CROSSING_MIN_PULSE_MS, scene_name=scene_name)
        return replace(msg, scene_name=scene_name)
