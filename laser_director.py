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
4. Not playing           -> safe_scene
5. Position stale        -> safe_scene
6. Default               -> default_scene
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .laser_models import LaserContext, LaserSceneDecision

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
    ) -> None:
        self._dry_run = dry_run
        self._enabled = enabled
        self._safe_scene = safe_scene
        self._default_scene = default_scene
        self._emergency_scene = emergency_scene

        # Mutable policy state — written only from the StateManager thread.
        self._emergency: bool = False
        self._manual_override_scene: Optional[str] = None
        self._manual_override_expires_at: float = 0.0
        self._current_scene: str = ""
        self._last_reason: str = ""
        self._last_error: str = ""

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

    # ── Tick (called from StateManager._push_tick) ────────────────────────────

    def tick(self, ctx: LaserContext, *, now: float) -> None:
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
            return

        decision = self._decide(ctx, now=now)

        if decision.scene != self._current_scene or decision.reason != self._last_reason:
            log.info(
                "[LASER] scene  %s->%s  reason=%s  dry_run=%s",
                self._current_scene or "(none)",
                decision.scene,
                decision.reason,
                self._dry_run,
            )

        self._current_scene = decision.scene
        self._last_reason = decision.reason

    def _decide(self, ctx: LaserContext, *, now: float) -> LaserSceneDecision:
        """Priority-ordered scene selection. Returns a LaserSceneDecision."""

        # Priority 1: Emergency blackout (latched; bypasses all other gates).
        if self._emergency:
            return LaserSceneDecision(
                scene=self._emergency_scene,
                reason="emergency",
                priority=1,
                source="emergency",
            )

        # Priority 2: Manual override (TTL-bounded).
        if self._manual_override_scene is not None:
            if now <= self._manual_override_expires_at:
                return LaserSceneDecision(
                    scene=self._manual_override_scene,
                    reason="manual_override",
                    priority=2,
                    source="manual",
                )
            # TTL expired — clear it and fall through.
            self.clear_manual_override()

        # Priority 3: Not playing.
        if not ctx.playing:
            return LaserSceneDecision(
                scene=self._safe_scene,
                reason="not_playing",
                priority=3,
                source="policy",
            )

        # Priority 4: Stale position.
        if ctx.position_stale:
            return LaserSceneDecision(
                scene=self._safe_scene,
                reason="position_stale",
                priority=4,
                source="policy",
            )

        # Priority 5: Default (playing with fresh position).
        return LaserSceneDecision(
            scene=self._default_scene,
            reason="default",
            priority=5,
            source="policy",
        )

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
        }
