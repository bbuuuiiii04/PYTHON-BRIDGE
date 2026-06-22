"""Immutable SoundSwitch pack runtime bundle (T7e).

One frozen snapshot of the live pack runtime — player, controller input, output
backend, and frame sender — published to the StateManager 200 Hz push loop by a
SINGLE atomic attribute assignment (`self._pack_runtime = new`). The push loop
reads exactly one reference per tick, so it never observes a mixed old/new runtime
(e.g. an old player with a new backend). Building a bundle does no I/O; the command
thread does all blocking work (load_pack, serial open/close) before publishing.

Status exposed from here is SANITIZED: no paths, ports, aliases, device names,
fixture maps, UUIDs, or raw exception messages (T7e §B1/C7/C10).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PackRuntime:
    enabled: bool = False
    reason: str = "disabled"          # sanitized category, never a raw message
    player: Any = None                # LaserPackPlayer | None
    midi_input: Any = None            # SoundSwitchMidiInputGroup | None
    backend: Any = None               # LaserOutputBackend | None
    frame_sender: Any = None          # SoundSwitchFrameSender | None
    pack_sha12: str = ""              # first 12 of the public manifest sha; "" if none

    @property
    def active(self) -> bool:
        """True only when output should be driven: explicitly enabled with a
        player and backend present. Disabled/none/missing -> False -> driver inert."""
        return bool(self.enabled and self.player is not None and self.backend is not None)

    def sanitized_status(self) -> dict[str, Any]:
        """Sanitized status dict (no paths/ports/aliases/devices/UUIDs/raw errors)."""
        backend_name = "disabled"
        frame_count = 0
        has_active_identity = False
        if self.backend is not None:
            try:
                raw = self.backend.status()
            except Exception:
                raw = {}
            backend_name = str(raw.get("backend", "unknown"))
            fc = raw.get("frame_count", 0)
            frame_count = int(fc) if isinstance(fc, int) else 0
            has_active_identity = bool(raw.get("last_accepted_identity"))
        return {
            "available": self.player is not None or self.backend is not None,
            "enabled": bool(self.enabled),
            "backend": backend_name if self.enabled else "disabled",
            "pack_loaded": self.player is not None,
            "pack_sha12": self.pack_sha12 or "",
            "frame_count": frame_count,
            "has_active_identity": has_active_identity,
            "reason": self.reason,           # sanitized category only
        }


# A shared disabled/no-output runtime — driver inert, no DMX.
DISABLED_PACK_RUNTIME = PackRuntime()
