"""SoundSwitch scripted timeline cue-reference resolution.

Serialized timeline references resolve EXACTLY against the file's own
``(GUID, stored_key)`` dictionary: reference ``R`` resolves to the record
with ``stored_key == R``, and ``R == 0`` is the reserved OFF/clear sentinel
(zero every channel except the verified control channels 8/9/11).

Evidence (capture ``parity_20260701T185231Z``, 2026-07-02 byte-proof, 261/261
fixture rows): the shipped pipeline carried TWO off-by-one errors that
cancelled on venue-ordered dictionaries — this exact-key resolution PLUS a
precede-association correction to venue cue attribute values (see
``soundswitch_project_decoder.decode_venue_cues``). Isolating resolution
alone (as previously read, ``stored_key == R - 1`` against the OLD
value association) reproduced only 195/261 rows; the combined correction
reproduces all 261/261, including the 66 previously-lit divergent samples
(19 autoloop + 47 scripted) in the committed parity fixtures. This supersedes
the prior ``R - 1`` reading, which was a bridge-side reconciliation for a
value-association bug rather than a true resolution rule. A positive
reference whose ``R`` key is absent is a miss: the event resolves to no cue
and the prior held frame continues (skip-hold).
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

    ``raw_reference`` resolves EXACTLY against the dictionary's stored keys;
    zero is the OFF/clear sentinel.  A miss yields ``resolved_cue_guid=None``
    (the renderer then skips the event and holds the prior frame).
    """
    if raw_reference == 0:
        return ScriptedReferenceResolution("clear_control", None, None)
    key = raw_reference
    return ScriptedReferenceResolution("cue", key, key_to_guid.get(key))


__all__ = ["ScriptedReferenceResolution", "resolve_scripted_reference"]
