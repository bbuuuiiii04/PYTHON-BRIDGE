"""I/O-free native SoundSwitch Autoloop selection and phase resolver."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .config import AUTOLOOP_ARM_PHRASE_BEATS
from .laser_models import LaserResolvedScene
from .soundswitch_laser_player import PlayerResult, ZERO_FRAME
from .soundswitch_pack_loader import AUTOLOOP_CYCLE_TICKS, LoadedAutoloopBinding

AUTOLOOP_TICKS_PER_BEAT = AUTOLOOP_CYCLE_TICKS // AUTOLOOP_ARM_PHRASE_BEATS

NATIVE_AUTOLOOP_STATUSES = frozenset((
    "rendering_active",
    "empty_dark_look",
    "missing_binding",
    "missing_autoloop_file",
    "unsupported_layout",
    "soundswitch_present_native_suppressed",
    "software_zero_frame",
))


@dataclass(frozen=True, slots=True)
class NativeAutoloopState:
    pack_sha12: str
    role: str
    scene: str
    note: int
    soundswitch_name: str
    target_identity: str
    anchor_beat: float


@dataclass(frozen=True, slots=True)
class NativeAutoloopDecision:
    status: str
    state: NativeAutoloopState | None = None
    role: str = ""
    scene: str = ""
    note: int | None = None
    soundswitch_name: str = ""
    target_identity: str = ""
    anchor_beat: float | None = None
    phase_tick: int | None = None
    reason: str = ""
    diagnostic: str = ""

    def to_status_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "role": self.role,
            "scene": self.scene,
            "note": self.note,
            "soundswitch_name": self.soundswitch_name,
            "target_identity": self.target_identity,
            "anchor_beat": self.anchor_beat,
            "phase_tick": self.phase_tick,
            "reason": self.reason,
            "diagnostic": self.diagnostic,
        }


def _phase_tick(abs_beat_pos: float, anchor_beat: float, phase_offset_beats: float) -> int:
    return round(
        ((float(abs_beat_pos) - float(anchor_beat) + float(phase_offset_beats))
         % AUTOLOOP_ARM_PHRASE_BEATS)
        * AUTOLOOP_TICKS_PER_BEAT
    )


def _decision_from_state(
    status: str,
    state: NativeAutoloopState,
    *,
    abs_beat_pos: float,
    phase_offset_beats: float,
    reason: str,
    diagnostic: str = "",
) -> NativeAutoloopDecision:
    phase_tick = _phase_tick(abs_beat_pos, state.anchor_beat, phase_offset_beats)
    return NativeAutoloopDecision(
        status=status,
        state=state,
        role=state.role,
        scene=state.scene,
        note=state.note,
        soundswitch_name=state.soundswitch_name,
        target_identity=state.target_identity,
        anchor_beat=state.anchor_beat,
        phase_tick=phase_tick,
        reason=reason,
        diagnostic=diagnostic,
    )


def finalize_native_autoloop_render(
    decision: NativeAutoloopDecision,
    result: PlayerResult,
) -> NativeAutoloopDecision:
    """Map pack-player render diagnostics onto native Autoloop status."""
    if decision.state is None:
        return decision
    diagnostic = result.diagnostic.code if result.diagnostic is not None else ""
    if diagnostic == "autoloop_not_found":
        return replace(decision, status="missing_autoloop_file", diagnostic=diagnostic)
    if diagnostic in ("inactive_autoloop", "unsupported_layout"):
        return replace(decision, status="unsupported_layout", diagnostic=diagnostic)
    if diagnostic:
        return replace(decision, status="unsupported_layout", diagnostic=diagnostic)
    if result.frame == ZERO_FRAME:
        return NativeAutoloopDecision(
            status="empty_dark_look",
            state=decision.state,
            role=decision.role,
            scene=decision.scene,
            note=decision.note,
            soundswitch_name=decision.soundswitch_name,
            target_identity=decision.target_identity,
            anchor_beat=decision.anchor_beat,
            phase_tick=decision.phase_tick,
            reason=decision.reason,
            diagnostic=diagnostic,
        )
    return decision


class NativeAutoloopResolver:
    """Tiny state holder for the selected native Autoloop and anchor beat."""

    def __init__(self) -> None:
        self._state: NativeAutoloopState | None = None

    @property
    def state(self) -> NativeAutoloopState | None:
        return self._state

    def reset(self) -> None:
        self._state = None

    def resolve(
        self,
        *,
        pack_sha12: str,
        bindings: Mapping[tuple[int, int], LoadedAutoloopBinding],
        scene: LaserResolvedScene | None,
        lighting_mode: str,
        scripted_active: bool,
        playing: bool,
        fresh: bool,
        track_changed: bool,
        discontinuity: bool,
        soundswitch_present: bool,
        abs_beat_pos: float,
        phase_offset_beats: float = 0.0,
    ) -> NativeAutoloopDecision:
        if soundswitch_present:
            self.reset()
            return NativeAutoloopDecision(
                "soundswitch_present_native_suppressed",
                reason="soundswitch_present",
            )
        if (
            lighting_mode != "autoloop"
            or scripted_active
            or not playing
            or not fresh
            or track_changed
            or discontinuity
        ):
            self.reset()
            return NativeAutoloopDecision("software_zero_frame", reason="ineligible")

        if self._state is not None and self._state.pack_sha12 != pack_sha12:
            self.reset()

        if scene is not None:
            key = (int(scene.channel) - 1, int(scene.note))
            binding = bindings.get(key)
            if binding is None:
                self.reset()
                return NativeAutoloopDecision(
                    "missing_binding",
                    role=scene.role,
                    scene=scene.scene,
                    note=int(scene.note),
                    reason=scene.reason,
                    diagnostic=f"missing_binding:{key[0]}:{key[1]}",
                )
            self._state = NativeAutoloopState(
                pack_sha12=pack_sha12,
                role=scene.role,
                scene=scene.scene,
                note=int(scene.note),
                soundswitch_name=binding.target_name,
                target_identity=binding.target_identity,
                anchor_beat=float(abs_beat_pos),
            )

        if self._state is None:
            return NativeAutoloopDecision("software_zero_frame", reason="waiting_for_edge")

        return _decision_from_state(
            "rendering_active",
            self._state,
            abs_beat_pos=abs_beat_pos,
            phase_offset_beats=phase_offset_beats,
            reason=scene.reason if scene is not None else "latched",
        )


__all__ = [
    "AUTOLOOP_TICKS_PER_BEAT",
    "NATIVE_AUTOLOOP_STATUSES",
    "NativeAutoloopDecision",
    "NativeAutoloopResolver",
    "NativeAutoloopState",
    "finalize_native_autoloop_render",
]
