"""SoundSwitch scripted timeline cue-reference resolution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


@dataclass(frozen=True, slots=True)
class ScriptedReferenceResolution:
    reference_kind: Literal["clear_control", "cue"]
    resolved_stored_key: int | None
    resolved_cue_guid: str | None


def resolve_scripted_reference(
    raw_reference: int,
    key_to_guid: Mapping[int, str],
) -> ScriptedReferenceResolution:
    """Resolve a timeline raw_reference by exact serialized-key lookup.

    SoundSwitch U0 playback looks up the positive raw value in the file's own
    saved key map. Raw zero is a clear/control sentinel, not cue key zero.
    """
    if raw_reference == 0:
        return ScriptedReferenceResolution("clear_control", None, None)
    guid = key_to_guid.get(raw_reference)
    return ScriptedReferenceResolution("cue", raw_reference, guid)


__all__ = ["ScriptedReferenceResolution", "resolve_scripted_reference"]
