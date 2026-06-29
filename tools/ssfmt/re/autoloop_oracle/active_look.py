"""Resolve which SoundSwitch Autoloop look is active at capture time."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import bisect
import json
from pathlib import Path
import re
import sys

from .phase_track import PhaseSample, beat_at

IAC_BUS = "IAC Driver Bus 1"
AUTOLOOP_GUARD_BEATS = 32.0
UNRELIABLE_GROUNDTRUTH = "UNRELIABLE_GROUNDTRUTH"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TIME = re.compile(r"(\d\d):(\d\d):(\d\d)\.(\d+)")
_LX_FIRE = re.compile(r"\[LX\]\s+fired\b.*\bnote=(\d+)\b")


@dataclass(frozen=True, slots=True)
class LookEvent:
    epoch_s: float
    note: int
    look: str
    abs_beat_pos: float | None
    source: str


@dataclass(frozen=True, slots=True)
class LookSelection:
    look: str | None
    reason: str | None = None
    note: int | None = None
    event_epoch_s: float | None = None
    beats_since_event: float | None = None


def _repo_parent() -> Path:
    return Path(__file__).resolve().parents[5]


def _ensure_repo_parent_on_path() -> None:
    parent = str(_repo_parent())
    if parent not in sys.path:
        sys.path.insert(0, parent)


def note_to_autoloop_from_project(project_path: str | Path) -> dict[int, str]:
    """Decode with ``soundswitch_project_decoder.decode_project`` and map IAC notes."""
    _ensure_repo_parent_on_path()
    from rb_ss_bridge_v2.soundswitch_project_decoder import decode_project

    decoded = decode_project(project_path)
    result: dict[int, str] = {}
    for row in decoded.resolved_controls:
        binding = row.binding
        if (
            binding.enabled
            and row.target_kind == "autoloop"
            and binding.message_type == "note"
            and binding.device_name == IAC_BUS
            and row.target_identity
        ):
            result[int(binding.data_byte)] = row.target_identity
    return result


def note_to_autoloop_from_pack(pack_path: str | Path) -> dict[int, str]:
    path = Path(pack_path) / "selection_map.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    result: dict[int, str] = {}
    for row in value.get("iac_selections", ()):
        if (
            row.get("active") is True
            and row.get("device_name") == IAC_BUS
            and row.get("message_type") == "note"
            and row.get("target_kind") == "autoloop"
            and row.get("target_identity")
        ):
            result[int(row["data_byte"])] = str(row["target_identity"])
    return result


def build_note_to_autoloop(project_or_pack: str | Path) -> dict[int, str]:
    root = Path(project_or_pack).expanduser()
    if (root / "selection_map.json").is_file():
        return note_to_autoloop_from_pack(root)
    return note_to_autoloop_from_project(root)


def _nearest_local_epoch(log_time: re.Match[str], epoch_hint_s: float) -> float:
    hint = datetime.fromtimestamp(epoch_hint_s)
    fraction = log_time.group(4)
    microsecond = int((fraction + "000000")[:6])
    candidate = hint.replace(
        hour=int(log_time.group(1)),
        minute=int(log_time.group(2)),
        second=int(log_time.group(3)),
        microsecond=microsecond,
    )
    choices = (candidate - timedelta(days=1), candidate, candidate + timedelta(days=1))
    return min(choices, key=lambda item: abs(item.timestamp() - epoch_hint_s)).timestamp()


def load_bridge_log_events(
    bridge_log: str | Path,
    note_to_autoloop: dict[int, str],
    *,
    epoch_hint_s: float,
    samples: list[PhaseSample] | None = None,
) -> list[LookEvent]:
    events: list[LookEvent] = []
    with Path(bridge_log).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = _ANSI.sub("", line)
            time_match = _TIME.search(line)
            fire_match = _LX_FIRE.search(line)
            if time_match is None or fire_match is None:
                continue
            note = int(fire_match.group(1))
            look = note_to_autoloop.get(note)
            if look is None:
                continue
            epoch_s = _nearest_local_epoch(time_match, epoch_hint_s)
            events.append(LookEvent(
                epoch_s=epoch_s,
                note=note,
                look=look,
                abs_beat_pos=beat_at(samples, epoch_s) if samples else None,
                source="bridge.log",
            ))
    events.sort(key=lambda event: event.epoch_s)
    return events


class ActiveLookResolver:
    def __init__(self, events: list[LookEvent]):
        self._events = sorted(events, key=lambda event: event.epoch_s)
        self._times = [event.epoch_s for event in self._events]

    @classmethod
    def from_phase_and_log(
        cls,
        samples: list[PhaseSample],
        note_to_autoloop: dict[int, str],
        bridge_log: str | Path | None,
    ) -> "ActiveLookResolver":
        events = [
            LookEvent(
                epoch_s=sample.epoch_s,
                note=sample.accepted_note,
                look=note_to_autoloop[sample.accepted_note],
                abs_beat_pos=sample.abs_beat_pos,
                source="accepted_note",
            )
            for sample in samples
            if sample.accepted_note is not None and sample.accepted_note in note_to_autoloop
        ]
        if bridge_log is not None and samples:
            events.extend(load_bridge_log_events(
                bridge_log,
                note_to_autoloop,
                epoch_hint_s=samples[0].epoch_s,
                samples=samples,
            ))
        return cls(events)

    def selection_at(self, t: float, abs_beat: float | None = None) -> LookSelection:
        index = bisect.bisect_right(self._times, t) - 1
        if index < 0:
            return LookSelection(None, "idle")
        event = self._events[index]
        beats_since = None
        if abs_beat is not None and event.abs_beat_pos is not None:
            beats_since = abs_beat - event.abs_beat_pos
            if beats_since > AUTOLOOP_GUARD_BEATS:
                return LookSelection(
                    None,
                    UNRELIABLE_GROUNDTRUTH,
                    event.note,
                    event.epoch_s,
                    beats_since,
                )
        return LookSelection(event.look, None, event.note, event.epoch_s, beats_since)

    def active_look_at(self, t: float) -> str | None:
        return self.selection_at(t).look
