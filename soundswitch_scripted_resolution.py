"""SoundSwitch scripted timeline cue-reference resolution.

Serialized timeline references live in a 1-based space over the file's own
0-based ``(GUID, stored_key)`` dictionary: reference ``R`` resolves to the
record with ``stored_key == R - 1``, and ``R == 0`` is the reserved OFF/clear
sentinel (zero every channel except the verified control channels 8/9/11).

Evidence (capture ``parity_20260701T185231Z``, 2026-07-02 pass): under this
rule the fresh exports of ``{528E8B22...}`` and ``{9947C65E...}`` reproduce
SoundSwitch U0 byte-exactly for 100.0% of their captured dwell (0.0% under
``stored_key == R``); ``{FC10FC02...}`` pitch-locks 11 consecutive events to
<20 ms; ``{AE9E3C61...}`` matches every boundary whose cue set is present in
the file on disk.  The recorded Ghidra packet's "no subtraction" finding
describes the exact-key lookup inside SoundSwitch's own resolved map; the
bridge's ``stored_key`` is the file's 0-based writer index, one below the
1-based serialized reference space.  A positive reference whose ``R - 1`` key
is absent is a miss: the event resolves to no cue and the prior held frame
continues (skip-hold).
"""
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
    """Resolve a serialized timeline reference against the file's own key map.

    ``raw_reference`` is 1-based over the dictionary's 0-based stored keys;
    zero is the OFF/clear sentinel.  A miss yields ``resolved_cue_guid=None``
    (the renderer then skips the event and holds the prior frame).
    """
    if raw_reference == 0:
        return ScriptedReferenceResolution("clear_control", None, None)
    key = raw_reference - 1
    return ScriptedReferenceResolution("cue", key, key_to_guid.get(key))


__all__ = ["ScriptedReferenceResolution", "resolve_scripted_reference"]
