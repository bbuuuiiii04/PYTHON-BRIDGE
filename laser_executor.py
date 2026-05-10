"""LaserSceneExecutor — resolves policy decisions into MIDI triggers.

This module intentionally keeps policy selection in LaserDirector while owning:
- role bank rotation (deterministic round-robin),
- scene lookup in validated LaserConfig,
- execution gates for live-safe triggering, and
- delegation to MidiOutput.trigger().
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .laser_config import LaserConfig
from .laser_models import LaserContext, LaserPersonality, LaserSceneDecision
from .midi_output import MidiOutput

_AUTO_ROLES = ("phrase", "buildup", "drop", "post_drop", "breakdown")
_PHRASE_TRIGGER_REASONS = frozenset({"default_init", "phrase_boundary"})


class LaserSceneExecutor:
    """Non-blocking decision executor for Laser Director."""

    def __init__(
        self,
        *,
        config: LaserConfig,
        midi_output: MidiOutput,
        personality: Optional[LaserPersonality],
    ) -> None:
        self._config = config
        self._midi_output = midi_output
        self._personality = personality
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
        self._role_cursors = {role: 0 for role in _AUTO_ROLES}
        self._role_active_scene = {role: "" for role in _AUTO_ROLES}

    def set_personality(self, personality: Optional[LaserPersonality]) -> None:
        """Switch executor personality and reset role-bank execution state."""
        with self._lock:
            self._personality = personality
            self._last_role = "idle"
            self._last_reason = ""
            self._last_triggered_scene = ""
            self._last_error = ""
            self._role_cursors = {role: 0 for role in _AUTO_ROLES}
            self._role_active_scene = {role: "" for role in _AUTO_ROLES}

    def on_decision(self, decision: Optional[LaserSceneDecision], ctx: LaserContext) -> None:
        """Consume one decision and trigger MIDI when all gates pass."""
        if decision is None:
            return

        role = decision.role or "idle"
        with self._lock:
            previous_role = self._last_role
            role_changed = role != previous_role
            if role_changed:
                if previous_role in self._role_active_scene:
                    self._role_active_scene[previous_role] = ""
                self._last_role = role
            self._last_reason = decision.reason

        if role == "idle" or not decision.scene:
            return

        selected_scene = self._select_scene(decision, ctx, role_changed)
        if not selected_scene:
            return

        if role in _AUTO_ROLES and not self._passes_automatic_gates(ctx):
            self._record_gate("auto_gate_blocked")
            return

        scene_def = self._config.scenes.get(selected_scene)
        if scene_def is None:
            with self._lock:
                self._missing_scene_count += 1
                self._gated_count += 1
                self._last_error = f"missing_scene_mapping:{selected_scene}"
            return

        allow_high_impact = bool(
            self._personality.allow_high_impact if self._personality is not None else False
        )
        if role != "emergency" and scene_def.safety_class == "high_impact" and not allow_high_impact:
            self._record_gate("high_impact_blocked")
            return

        with self._lock:
            if selected_scene == self._last_triggered_scene:
                self._same_scene_skip_count += 1
                return

        priority = self._priority_for_role(role)
        if not self._midi_output.trigger(scene_def.midi, priority=priority):
            self._record_gate("midi_trigger_rejected")
            return

        with self._lock:
            self._triggered_count += 1
            self._last_triggered_scene = selected_scene
            self._last_trigger_at = time.monotonic()
            self._last_error = ""

    def status(self) -> dict:
        with self._lock:
            role_cursors = dict(self._role_cursors)
            active_scenes = dict(self._role_active_scene)
            return {
                "dry_run": self._config.dry_run,
                "last_role": self._last_role,
                "last_reason": self._last_reason,
                "last_scene": self._last_triggered_scene,
                "last_trigger_at": self._last_trigger_at,
                "last_error": self._last_error,
                "triggered_count": self._triggered_count,
                "gated_count": self._gated_count,
                "missing_scene_count": self._missing_scene_count,
                "same_scene_skip_count": self._same_scene_skip_count,
                "role_cursors": role_cursors,
                "role_active_scenes": active_scenes,
                "midi": self._midi_output.status(),
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

        with self._lock:
            if role == "phrase":
                if decision.reason not in _PHRASE_TRIGGER_REASONS:
                    return ""
                # Phrase/default should only trigger on real autoloop phrase edges.
                if decision.reason == "phrase_boundary" and not ctx.autoloop_tick_just_fired:
                    return ""
                return self._choose_bank_scene_locked(role=role, fallback_scene=decision.scene)

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

    def _bank_for_role(self, role: str) -> tuple[str, ...]:
        personality = self._personality
        if personality is None:
            return ()
        if role == "phrase":
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

    def _priority_for_role(self, role: str) -> str:
        if role in ("emergency", "manual", "drop"):
            return "high"
        return "normal"
