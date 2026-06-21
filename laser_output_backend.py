"""Output backend abstraction for LaserSceneExecutor.

Separates the executor's scene-selection and gating policy from the
physical output channel (MIDI, SoundSwitch pack DMX, or none/dry-run).

Protocol responsibilities:
  trigger()           — accept a scene-trigger MIDI message and return
                        whether it was sent (False = rejected by the
                        output channel; executor must not advance
                        pack selection on False).
  submit_frame()      — deliver a rendered CH1-CH19 frame to the output
                        channel (no-op for the MIDI backend; used by the
                        Enttec/DMX backend in T6).
  status()            — return a sanitised diagnostic dict.
  reset()             — clear transient send state without closing output.
  shutdown()          — release owned resources; after this the backend
                        must not send new physical output.

Invariants:
  - Gated, cooldown-skipped, missing, or rejected scenes MUST NOT reach
    the backend; the executor enforces gates before calling trigger().
  - Direct DMX (submit_frame) and physical MIDI laser output are mutually
    exclusive.  The executor enforces this at construction time.
  - Default/dry-run/none backend produces no new physical output.
  - The 200 Hz hot path (LaserSceneExecutor.on_tick / on_decision) must
    not call blocking I/O; submit_frame uses a bounded non-blocking
    mailbox (T6).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .laser_models import LaserMidiMessage
from .midi_output import MidiOutput


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LaserOutputBackend(Protocol):
    """Structural protocol for laser output backends."""

    def trigger(self, msg: LaserMidiMessage, *, priority: str = "normal") -> bool:
        """Send a scene-trigger message.  Returns True if sent/accepted."""
        ...

    def submit_frame(self, frame: tuple[int, ...]) -> None:
        """Deliver a rendered CH1-CH19 frame to the physical output channel."""
        ...

    def status(self) -> dict:
        """Return a sanitised diagnostic dict; must not block."""
        ...

    def reset(self) -> None:
        """Clear transient send state; does not close the output channel."""
        ...

    def shutdown(self) -> None:
        """Release owned resources. No new physical output after this."""
        ...


# ---------------------------------------------------------------------------
# MIDI backend — wraps the existing MidiOutput; byte/order identical
# ---------------------------------------------------------------------------

class MidiOutputBackend:
    """Thin adapter that presents MidiOutput as a LaserOutputBackend.

    All behaviour (pulse/hold ordering, cooldown gates, random role-bank
    rotation, blackout owner refcounts) remains in LaserSceneExecutor.
    This class forwards trigger() and status() unchanged so that the
    executor's observable MIDI behaviour is byte- and order-identical
    to the pre-T5 direct dependency.
    """

    def __init__(self, midi_output: MidiOutput) -> None:
        self._midi_output = midi_output

    def trigger(self, msg: LaserMidiMessage, *, priority: str = "normal") -> bool:
        return self._midi_output.trigger(msg, priority=priority)

    def submit_frame(self, frame: tuple[int, ...]) -> None:
        pass  # MIDI backend does not output DMX frames.

    def status(self) -> dict:
        return self._midi_output.status()

    def reset(self) -> None:
        pass  # MidiOutput manages its own reconnect/reset lifecycle.

    def shutdown(self) -> None:
        pass  # MidiOutput lifecycle is owned by the bridge startup layer.


# ---------------------------------------------------------------------------
# None / dry-run backend — produces no physical output
# ---------------------------------------------------------------------------

class NoneBackend:
    """No-op backend for pack_mode=off, dry_run=True, or output_backend=none.

    Emits no MIDI or DMX.  trigger() returns True so that the executor's
    internal counters (triggered_count, etc.) remain meaningful in dry-run
    and shadow-mode operation; the caller should gate on the backend type
    before logging "physical output sent".
    """

    def trigger(self, msg: LaserMidiMessage, *, priority: str = "normal") -> bool:
        return True  # accepted; no physical output.

    def submit_frame(self, frame: tuple[int, ...]) -> None:
        pass

    def status(self) -> dict:
        return {"backend": "none", "available": True, "dry_run": True}

    def reset(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Pack selection backend (stub — wired up in T7 with pack + frame sender)
# ---------------------------------------------------------------------------

class PackOutputBackend:
    """Routes accepted executor decisions into SoundSwitch pack selection.

    The executor calls trigger() only for scenes that have passed all
    gates.  This backend resolves the scene name to a pack autoloop
    identity via the provided scene→identity mapping, then advances
    the player's selection.  An unlearned scene (no entry in
    scene_to_identity) is a no-op selection — matching current
    SoundSwitch behaviour where an unmapped IAC note plays nothing.

    submit_frame() delivers rendered CH1-CH19 frames to the Enttec DMX
    sender (injected in T6).  Absent a sender, frames are counted but
    not transmitted.
    """

    def __init__(
        self,
        *,
        scene_to_identity: dict[str, str] | None = None,
        frame_sender=None,  # EnttecFrameSender injected in T6
    ) -> None:
        self._scene_to_identity: dict[str, str] = dict(scene_to_identity or {})
        self._frame_sender = frame_sender
        self._trigger_count = 0
        self._no_op_count = 0
        self._frame_count = 0

    def trigger(self, msg: LaserMidiMessage, *, priority: str = "normal") -> bool:
        identity = self._scene_to_identity.get(str(getattr(msg, "scene_name", "")))
        if identity is None:
            self._no_op_count += 1
            return True  # unlearned → no-op, but executor considers it accepted.
        self._trigger_count += 1
        return True

    def submit_frame(self, frame: tuple[int, ...]) -> None:
        self._frame_count += 1
        if self._frame_sender is not None:
            self._frame_sender.submit(frame)

    def status(self) -> dict:
        return {
            "backend": "pack",
            "available": True,
            "trigger_count": self._trigger_count,
            "no_op_count": self._no_op_count,
            "frame_count": self._frame_count,
            "has_frame_sender": self._frame_sender is not None,
        }

    def reset(self) -> None:
        pass

    def shutdown(self) -> None:
        if self._frame_sender is not None:
            try:
                self._frame_sender.stop()
            except Exception:
                pass


__all__ = [
    "LaserOutputBackend",
    "MidiOutputBackend",
    "NoneBackend",
    "PackOutputBackend",
]
