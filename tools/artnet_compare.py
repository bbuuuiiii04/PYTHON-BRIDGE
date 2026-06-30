#!/usr/bin/env python3
"""Observe SoundSwitch U0 and bridge truth-check U1 ArtDMX streams."""
from __future__ import annotations

import argparse
import hashlib
import json
import select
import socket
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.artnet_truth import ARTNET_PORT  # noqa: E402
from rb_ss_bridge_v2.soundswitch_frame_sender import _build_artdmx  # noqa: E402
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedPack, load_pack  # noqa: E402


VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_INCOMPLETE = "INCOMPLETE"
VERDICT_INVALID = "INVALID"


@dataclass(frozen=True)
class ArtDmxPacket:
    timestamp_ns: int
    universe: int
    sequence: int
    declared_length: int
    payload: bytes
    source: str = ""
    socket_name: str = ""
    valid_protocol: bool = True
    error: str = ""


@dataclass(frozen=True)
class CompareResult:
    verdict: str
    reason: str
    failure_class: str = ""
    matches: int = 0
    offsets_ms: tuple[float, ...] = ()
    duplicate_count: int = 0
    remaining_coverage: tuple[str, ...] = ()
    details: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        offsets = list(self.offsets_ms)
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "failure_class": self.failure_class,
            "matches": self.matches,
            "timing": _timing_summary(offsets),
            "duplicate_count": self.duplicate_count,
            "remaining_coverage": list(self.remaining_coverage),
            "details": list(self.details),
        }


def parse_artdmx(data: bytes, *, timestamp_ns: int, source: str = "", socket_name: str = "") -> ArtDmxPacket | None:
    if len(data) < 18 or data[:8] != b"Art-Net\x00":
        return None
    opcode = int.from_bytes(data[8:10], "little")
    if opcode != 0x5000:
        return None
    protocol = int.from_bytes(data[10:12], "big")
    sequence = data[12]
    universe = int.from_bytes(data[14:16], "little") & 0x7FFF
    declared_length = int.from_bytes(data[16:18], "big")
    payload = bytes(data[18:])
    if protocol < 14:
        return ArtDmxPacket(timestamp_ns, universe, sequence, declared_length, payload, source, socket_name, False, "protocol_version")
    if declared_length != len(payload) or declared_length != 512:
        return ArtDmxPacket(timestamp_ns, universe, sequence, declared_length, payload, source, socket_name, False, "packet_length")
    return ArtDmxPacket(timestamp_ns, universe, sequence, declared_length, payload, source, socket_name)


RAPID_EVENT_GAP_MS = 50
AUTOLOOP_PHASE_BUCKETS = 3
AUTOLOOP_CYCLE_TICKS = 19_200


def parse_sidecar_jsonl(text: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bool]:
    header: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    invalid = False
    for raw in text.splitlines(keepends=True):
        if not raw.endswith("\n"):
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            invalid = True
            continue
        if not isinstance(row, dict):
            invalid = True
            continue
        if row.get("type") == "header":
            header = row
        elif row.get("type") == "frame":
            if _sidecar_frame_schema_error(row):
                invalid = True
            else:
                rows.append(row)
        else:
            invalid = True
    return header, rows, invalid


def _has_partial_sidecar_tail(text: str) -> bool:
    return bool(text) and not text.endswith("\n") and bool(text.rsplit("\n", 1)[-1].strip())


def dedup_packets(
    packets: Iterable[ArtDmxPacket],
    *,
    window_ms: float = 10.0,
) -> tuple[list[ArtDmxPacket], int]:
    kept: list[ArtDmxPacket] = []
    duplicate_count = 0
    window_ns = int(window_ms * 1_000_000)
    for packet in sorted(packets, key=lambda item: item.timestamp_ns):
        duplicate = False
        for prior in reversed(kept[-8:]):
            if packet.timestamp_ns - prior.timestamp_ns > window_ns:
                break
            if (
                packet.socket_name
                and prior.socket_name
                and packet.socket_name != prior.socket_name
                and packet.universe == prior.universe
                and packet.sequence == prior.sequence
                and packet.declared_length == prior.declared_length
                and packet.payload == prior.payload
            ):
                duplicate = True
                break
        if duplicate:
            duplicate_count += 1
        else:
            kept.append(packet)
    return kept, duplicate_count


def evaluate_trace(
    packets: Iterable[ArtDmxPacket],
    *,
    ss_universe: int = 0,
    bridge_universe: int = 1,
    sidecar_rows: Sequence[Mapping[str, Any]] | Mapping[Any, Mapping[str, Any]] | None = None,
    sidecar_header: Mapping[str, Any] | None = None,
    bridge_status: Mapping[str, Any] | None = None,
    tolerance_ms: float = 5.0,
    required_coverage: Iterable[str] = (),
    sidecar_invalid: bool = False,
    sidecar_pending: bool = False,
    compare_overloaded: bool = False,
) -> CompareResult:
    packets, duplicate_count = dedup_packets(packets)
    malformed = [p for p in packets if not p.valid_protocol]
    if malformed:
        return CompareResult(VERDICT_INVALID, malformed[0].error, "SETUP_INVALID", duplicate_count=duplicate_count)
    u0 = [p for p in packets if p.universe == ss_universe]
    u1 = [p for p in packets if p.universe == bridge_universe]
    if not u0:
        return CompareResult(VERDICT_INVALID, "missing_u0", "SETUP_INVALID", duplicate_count=duplicate_count)
    if not u1:
        return CompareResult(VERDICT_INVALID, "missing_u1", "SETUP_INVALID", duplicate_count=duplicate_count)
    if sidecar_invalid or compare_overloaded:
        return CompareResult(VERDICT_INVALID, "sidecar_invalid" if sidecar_invalid else "compare_overload", "SETUP_INVALID", duplicate_count=duplicate_count)

    sidecar_rows = _ordered_sidecar_rows(sidecar_rows)
    bridge_status = bridge_status or {}
    status_truth = bridge_status.get("truth_check") if isinstance(bridge_status.get("truth_check"), dict) else {}
    status_run_raw = status_truth.get("run_id")
    header_run_raw = (sidecar_header or {}).get("run_id")
    status_run_id = status_run_raw if type(status_run_raw) is str else ""
    header_run_id = header_run_raw if type(header_run_raw) is str else ""
    if not status_run_id or not header_run_id:
        return CompareResult(VERDICT_INVALID, "run_id_missing", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
    if status_run_id != header_run_id:
        return CompareResult(VERDICT_INVALID, "run_id_mismatch", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
    if bool(status_truth.get("overflow_count")) or bool(status_truth.get("dropped_count")):
        return CompareResult(VERDICT_INVALID, "bridge_queue_overflow", "BRIDGE_QUEUE_OVERFLOW", duplicate_count=duplicate_count)
    if status_truth.get("sidecar_error"):
        return CompareResult(VERDICT_INVALID, "sidecar_error", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)

    seq_error = _u1_sequence_error(u1)
    if seq_error:
        return CompareResult(VERDICT_INVALID, seq_error, "U1_SEQUENCE_GAP", duplicate_count=duplicate_count)

    if _ambiguous_nearest_neighbor(u0, u1, int(tolerance_ms * 1_000_000)):
        return CompareResult(VERDICT_INVALID, "ambiguous_nearest_neighbor", "SETUP_INVALID", duplicate_count=duplicate_count)

    if len(u1) < len(u0):
        return CompareResult(VERDICT_INVALID, "missing_u1_frame", "SETUP_INVALID", matches=len(u1), duplicate_count=duplicate_count)
    if len(u1) > len(u0):
        return CompareResult(VERDICT_INVALID, "extra_u1_frame", "SETUP_INVALID", matches=len(u0), duplicate_count=duplicate_count)
    if len(sidecar_rows) > len(u1):
        return CompareResult(VERDICT_INVALID, "sidecar_unmatched_frame", "SIDECAR_MISSING_OR_STALE", matches=len(u1), duplicate_count=duplicate_count)

    offsets: list[float] = []
    details: list[dict[str, Any]] = []
    matched_rows: list[Mapping[str, Any]] = []
    tolerance_ns = int(tolerance_ms * 1_000_000)
    for index, ss_packet in enumerate(u0):
        bridge_packet = u1[index]
        sidecar_error, sidecar_row = _sidecar_row_for_packet(
            bridge_packet,
            index,
            sidecar_rows,
            status_run_id,
        )
        if sidecar_error:
            if sidecar_pending and sidecar_error.startswith("sidecar_missing:"):
                return CompareResult(
                    VERDICT_INCOMPLETE,
                    "sidecar_pending",
                    "COVERAGE_INCOMPLETE",
                    matches=index,
                    offsets_ms=tuple(offsets),
                    duplicate_count=duplicate_count,
                )
            return CompareResult(VERDICT_INVALID, sidecar_error, "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
        matched_rows.append(sidecar_row)
        offset_ns = bridge_packet.timestamp_ns - ss_packet.timestamp_ns
        offsets.append(offset_ns / 1_000_000.0)
        if abs(offset_ns) > tolerance_ns:
            return CompareResult(
                VERDICT_FAIL,
                "timing_mismatch",
                "TIMING_MISMATCH",
                matches=index,
                offsets_ms=tuple(offsets),
                duplicate_count=duplicate_count,
            )
        if bridge_packet.payload != ss_packet.payload:
            diff = _first_diffs(ss_packet.payload, bridge_packet.payload)
            details.append({"index": index, "diffs": diff, "total_diffs": _diff_count(ss_packet.payload, bridge_packet.payload)})
            if any(channel == 1 for channel, _a, _b in diff):
                failure_class = "VISIBLE_FLASH_OR_MISS"
            elif sorted(p.payload for p in u0[:len(u1)]) == sorted(p.payload for p in u1[:len(u0)]):
                failure_class = "ORDER_MISMATCH"
            else:
                failure_class = "HIDDEN_STATE_MISMATCH"
            return CompareResult(
                VERDICT_FAIL,
                "byte_mismatch",
                failure_class,
                matches=index,
                offsets_ms=tuple(offsets),
                duplicate_count=duplicate_count,
                details=tuple(details),
            )

    observed = _observed_coverage(matched_rows, required_coverage=required_coverage)
    remaining = tuple(sorted(set(required_coverage) - observed))
    if remaining:
        return CompareResult(
            VERDICT_INCOMPLETE,
            "coverage_missing",
            "COVERAGE_INCOMPLETE",
            matches=len(u0),
            offsets_ms=tuple(offsets),
            duplicate_count=duplicate_count,
            remaining_coverage=remaining,
        )
    return CompareResult(
        VERDICT_PASS,
        "matched",
        matches=len(u0),
        offsets_ms=tuple(offsets),
        duplicate_count=duplicate_count,
    )


def _u1_sequence_error(u1: list[ArtDmxPacket]) -> str:
    prev: int | None = None
    for packet in u1:
        if packet.sequence == 0:
            return "sequence_zero"
        if prev is not None:
            expected = 1 if prev == 255 else prev + 1
            if packet.sequence != expected:
                return f"sequence_gap:{prev}->{packet.sequence}"
        prev = packet.sequence
    return ""


def _ordered_sidecar_rows(
    rows: Sequence[Mapping[str, Any]] | Mapping[Any, Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    if rows is None:
        return []
    if isinstance(rows, Mapping):
        return sorted(
            rows.values(),
            key=lambda row: (
                _sort_int(row.get("frame_index")),
                _sort_int(row.get("sequence")),
            ),
        )
    return list(rows)


def _sort_int(value: Any) -> int:
    return value if type(value) is int else 0


def _sidecar_row_for_packet(
    packet: ArtDmxPacket,
    index: int,
    rows: Sequence[Mapping[str, Any]],
    run_id: str,
) -> tuple[str, Mapping[str, Any]]:
    if index >= len(rows):
        return f"sidecar_missing:{packet.sequence}", {}
    row = rows[index]
    schema_error = _sidecar_frame_schema_error(row)
    if schema_error:
        return schema_error, {}
    if run_id and str(row.get("run_id") or "") != run_id:
        return f"sidecar_run_id_mismatch:{packet.sequence}", {}
    if row.get("sequence") != packet.sequence:
        return f"sidecar_sequence_mismatch:{packet.sequence}", {}
    if row.get("frame_index") != index + 1:
        return f"sidecar_frame_index_mismatch:{packet.sequence}", {}
    expected_hash = hashlib.sha256(packet.payload).hexdigest()
    if row.get("dmx_sha256") != expected_hash:
        return f"sidecar_hash_mismatch:{packet.sequence}", {}
    return "", row


def _sidecar_frame_schema_error(row: Mapping[str, Any]) -> str:
    sequence = row.get("sequence")
    frame_index = row.get("frame_index")
    digest = row.get("dmx_sha256")
    run_id = row.get("run_id")
    if row.get("type") != "frame":
        return "sidecar_schema:type"
    if type(run_id) is not str or not run_id:
        return "sidecar_schema:run_id"
    if type(sequence) is not int or not 1 <= sequence <= 255:
        return "sidecar_schema:sequence"
    if type(frame_index) is not int or frame_index < 1:
        return "sidecar_schema:frame_index"
    if type(digest) is not str or len(digest) != 64:
        return "sidecar_schema:dmx_sha256"
    return ""


def _ambiguous_nearest_neighbor(
    u0: list[ArtDmxPacket],
    u1: list[ArtDmxPacket],
    tolerance_ns: int,
) -> bool:
    for packet in u0:
        candidates = sorted(
            abs(candidate.timestamp_ns - packet.timestamp_ns)
            for candidate in u1
            if abs(candidate.timestamp_ns - packet.timestamp_ns) <= tolerance_ns
        )
        if len(candidates) >= 2 and candidates[0] == candidates[1]:
            return True
    return False


def _first_diffs(a: bytes, b: bytes, limit: int = 8) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for index, (left, right) in enumerate(zip(a, b), 1):
        if left != right:
            out.append((index, left, right))
            if len(out) >= limit:
                break
    return out


def _diff_count(a: bytes, b: bytes) -> int:
    return sum(1 for left, right in zip(a, b) if left != right) + abs(len(a) - len(b))


def _timing_summary(offsets: list[float]) -> dict[str, Any]:
    if not offsets:
        return {"median_ms": None, "p95_ms": None, "max_abs_ms": None, "early": 0, "late": 0}
    ordered = sorted(abs(value) for value in offsets)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "median_ms": statistics.median(offsets),
        "p95_abs_ms": ordered[p95_index],
        "max_abs_ms": max(ordered),
        "early": sum(1 for value in offsets if value < 0),
        "late": sum(1 for value in offsets if value > 0),
    }


def build_coverage_ledger(pack: LoadedPack) -> set[str]:
    required: set[str] = set()
    scripted_ids: set[str] = set()
    for key, row in getattr(pack, "scripted", {}).items():
        if not bool(getattr(row, "supported_active", True)):
            continue
        scripted_id = str(getattr(row, "soundswitch_id", "") or key)
        scripted_ids.add(scripted_id)
        required.add(f"scripted:{scripted_id}")
        document = _scripted_document(row)
        events = _document_events(document)
        if events:
            required.add(f"scripted_start|{scripted_id}")
            required.add(f"scripted_end|{scripted_id}")
        for event in events:
            required.add(f"scripted_event|{scripted_id}|{_event_sig(event)}")
        for left, right in zip(events, events[1:]):
            if 0 < int(getattr(right, "time", 0)) - int(getattr(left, "time", 0)) <= RAPID_EVENT_GAP_MS:
                required.add(
                    f"scripted_rapid_pair|{scripted_id}|{_event_sig(left)}|{_event_sig(right)}"
                )

    autoloop_bases: set[str] = set()
    for binding in getattr(pack, "autoloop_bindings", {}).values():
        identity = str(binding.target_identity)
        required.add(f"autoloop:{identity}")
        cls = _autoloop_class(pack, identity)
        required.add(f"{cls}:{identity}")
        autoloop_bases.add(f"{cls}:{identity}")
        for bucket in range(AUTOLOOP_PHASE_BUCKETS):
            required.add(f"autoloop_phase:{identity}:{bucket}")

    static_slots = sorted({
        int(binding.target_slot)
        for binding in getattr(pack, "learned_midi_bindings", ())
        if binding.target_kind == "static_look" and binding.target_slot is not None
    })
    blackout_keys = sorted({
        _blackout_key(binding)
        for binding in getattr(pack, "learned_midi_bindings", ())
        if binding.target_kind == "blackout_mask"
    })
    bases: list[str] = []
    if scripted_ids:
        bases.append("scripted")
    bases.extend(sorted(autoloop_bases))
    for binding in getattr(pack, "learned_midi_bindings", ()):
        if binding.target_kind == "static_look" and binding.target_slot is not None:
            required.add(f"static:{binding.target_slot}")
        elif binding.target_kind == "blackout_mask":
            required.add(f"blackout:{_blackout_key(binding)}")
    for slot in static_slots:
        for base in bases:
            required.add(f"static_over|{base}|{slot}")
            required.add(f"static_release|{base}|{slot}")
    for key in blackout_keys:
        for base in bases:
            required.add(f"blackout_over|{base}|{key}")
            required.add(f"blackout_release|{base}|{key}")
    if scripted_ids and autoloop_bases:
        required.add("transition|mode|scripted->autoloop")
        required.add("transition|mode|autoloop->scripted")
        required.add("transition|deck|1->2")
        required.add("transition|deck|2->1")
    return required


def _scripted_document(row: Any) -> Any:
    return getattr(row, "document", row)


def _document_events(document: Any) -> list[Any]:
    events = list(getattr(document, "events", ()) or ())
    return sorted(events, key=lambda row: (int(getattr(row, "time", 0)), int(getattr(row, "source_order", 0))))


def _event_sig(event: Any) -> str:
    cue = getattr(event, "resolved_cue_guid", None) or getattr(event, "source_offset", "")
    return ":".join((
        str(int(getattr(event, "time", 0))),
        str(int(getattr(event, "source_order", 0))),
        str(getattr(event, "reference_kind", "")),
        str(cue),
    ))


def _autoloop_class(pack: LoadedPack, identity: str) -> str:
    loop = getattr(pack, "autoloops", {}).get(identity) if hasattr(getattr(pack, "autoloops", {}), "get") else None
    document = getattr(loop, "document", loop)
    for event in _document_events(document):
        frame = getattr(event, "boundary_frame", None)
        if isinstance(frame, tuple) and any(int(value or 0) > 0 for value in frame):
            return "autoloop_visible"
        for patch in getattr(event, "patch", ()) or ():
            if int(getattr(patch, "value", 0) or 0) > 0:
                return "autoloop_visible"
    return "autoloop_authored_dark"


def _blackout_key(binding: Any) -> str:
    return f"{int(binding.channel_zero_based)}:{int(binding.data_byte)}"


def _observed_coverage(
    rows: Iterable[Mapping[str, Any]],
    *,
    required_coverage: Iterable[str] = (),
) -> set[str]:
    observed: set[str] = set()
    required = set(required_coverage)
    scripted_events: dict[str, list[tuple[int, str]]] = {}
    rapid_pairs: list[tuple[str, str, str]] = []
    autoloop_classes: dict[str, str] = {}
    for item in required:
        if item.startswith("scripted_event|"):
            _prefix, track, sig = item.split("|", 2)
            time_raw = sig.split(":", 1)[0]
            scripted_events.setdefault(track, []).append((int(time_raw), item))
        elif item.startswith("scripted_rapid_pair|"):
            _prefix, track, left, right = item.split("|", 3)
            rapid_pairs.append((
                item,
                f"scripted_event|{track}|{left}",
                f"scripted_event|{track}|{right}",
            ))
        elif item.startswith("autoloop_visible:"):
            autoloop_classes[item.split(":", 1)[1]] = "autoloop_visible"
        elif item.startswith("autoloop_authored_dark:"):
            autoloop_classes[item.split(":", 1)[1]] = "autoloop_authored_dark"
    for values in scripted_events.values():
        values.sort()

    last_elapsed: dict[str, int] = {}
    last_base = ""
    last_base_kind = ""
    last_base_deck: int | None = None
    last_deck_base = ""
    last_static: set[int] = set()
    last_blackout: set[str] = set()
    scripted_started: set[str] = set()
    for row in rows:
        base = ""
        base_kind = ""
        if row.get("scripted_active") and row.get("soundswitch_id"):
            scripted_id = str(row["soundswitch_id"])
            observed.add(f"scripted:{scripted_id}")
            base = "scripted"
            base_kind = "scripted"
            elapsed = _int_or_none(row.get("elapsed_ms"))
            if elapsed is not None:
                if elapsed <= 250:
                    observed.add(f"scripted_start|{scripted_id}")
                    scripted_started.add(scripted_id)
                prior = last_elapsed.get(scripted_id)
                if scripted_id in scripted_started and prior is None:
                    last_elapsed[scripted_id] = elapsed
                elif scripted_id in scripted_started and elapsed >= prior:
                    lower = prior
                    for event_time, token in scripted_events.get(scripted_id, ()):
                        if lower <= event_time <= elapsed:
                            observed.add(token)
                    if scripted_events.get(scripted_id) and elapsed >= scripted_events[scripted_id][-1][0]:
                        observed.add(f"scripted_end|{scripted_id}")
                    last_elapsed[scripted_id] = elapsed
        native = row.get("native_autoloop") if isinstance(row.get("native_autoloop"), dict) else {}
        native_status = str(native.get("status") or "") if isinstance(native, dict) else ""
        target = native.get("target_identity") if native_status in ("rendering_active", "empty_dark_look") else ""
        if target:
            target = str(target)
            observed.add(f"autoloop:{target}")
            cls = autoloop_classes.get(
                target,
                "autoloop_visible" if bool(row.get("visible")) else "autoloop_authored_dark",
            )
            observed.add(f"{cls}:{target}")
            base = f"{cls}:{target}"
            base_kind = "autoloop"
            phase_tick = _int_or_none(native.get("phase_tick"))
            if phase_tick is not None:
                bucket = min(
                    AUTOLOOP_PHASE_BUCKETS - 1,
                    int((phase_tick % AUTOLOOP_CYCLE_TICKS) / (AUTOLOOP_CYCLE_TICKS / AUTOLOOP_PHASE_BUCKETS)),
                )
                observed.add(f"autoloop_phase:{target}:{bucket}")

        static_slots = {int(slot) for slot in (row.get("static_slots") or ()) if type(slot) is int}
        for slot in static_slots:
            observed.add(f"static:{slot}")
            if base:
                observed.add(f"static_over|{base}|{slot}")
        blackout_keys = {str(key) for key in (row.get("blackout_bindings") or ())}
        if row.get("blackout"):
            for key in blackout_keys:
                observed.add(f"blackout:{key}")
                if base:
                    observed.add(f"blackout_over|{base}|{key}")

        if base and base == last_base:
            for slot in last_static - static_slots:
                observed.add(f"static_release|{base}|{slot}")
            for key in last_blackout - blackout_keys:
                observed.add(f"blackout_release|{base}|{key}")

        deck = _int_or_none(row.get("active_deck"))
        if base and last_deck_base and deck in (1, 2) and last_base_deck in (1, 2) and deck != last_base_deck:
            observed.add(f"transition|deck|{last_base_deck}->{deck}")
        if base_kind and last_base_kind and base_kind != last_base_kind:
            observed.add(f"transition|mode|{last_base_kind}->{base_kind}")

        if base:
            last_base = base
            last_base_kind = base_kind
            last_static = static_slots
            last_blackout = blackout_keys if row.get("blackout") else set()
            if deck in (1, 2):
                last_deck_base = base
                last_base_deck = deck
    for token, left, right in rapid_pairs:
        if left in observed and right in observed:
            observed.add(token)
    return observed


def _int_or_none(value: Any) -> int | None:
    return value if type(value) is int else None


def _packet(universe: int, payload: bytes, timestamp_ns: int, sequence: int = 1, socket_name: str = "lo") -> ArtDmxPacket:
    parsed = parse_artdmx(_build_artdmx(universe, payload, sequence), timestamp_ns=timestamp_ns, socket_name=socket_name)
    assert parsed is not None
    return parsed


def run_self_check() -> None:
    base = bytes([7]) + bytes(511)
    hidden = bytes([0, 99]) + bytes(510)
    run_id = "selfcheck"

    def row(packet: ArtDmxPacket, index: int = 1, *, stale: bool = False, **extra: Any) -> dict[str, Any]:
        out = {
            "type": "frame",
            "run_id": "old" if stale else run_id,
            "sequence": packet.sequence,
            "frame_index": index,
            "dmx_sha256": hashlib.sha256(packet.payload).hexdigest(),
            "scripted_active": True,
            "soundswitch_id": "script",
        }
        out.update(extra)
        return out

    def rows(*packets: ArtDmxPacket, stale: bool = False) -> list[dict[str, Any]]:
        return [
            row(packet, index, stale=stale)
            for index, packet in enumerate(packets, 1)
        ]

    status = {"truth_check": {"run_id": run_id, "overflow_count": 0, "dropped_count": 0, "sidecar_error": ""}}
    cases: list[tuple[str, CompareResult, str]] = []
    u0 = [_packet(0, base, 1_000_000_000, 0)]
    u1 = [_packet(1, base, 1_003_000_000, 1)]
    cases.append(("pass", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"scripted:script"}), VERDICT_PASS))
    cases.append(("byte_fail", evaluate_trace(u0 + [_packet(1, hidden, 1_003_000_000, 1)], sidecar_rows=rows(_packet(1, hidden, 1_003_000_000, 1)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_FAIL))
    cases.append(("timing_fail", evaluate_trace(u0 + [_packet(1, base, 1_020_000_000, 1)], sidecar_rows=rows(_packet(1, base, 1_020_000_000, 1)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_FAIL))
    cases.append(("order_fail", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, hidden, 1_010_000_000, 0), _packet(1, hidden, 1_003_000_000, 1), _packet(1, base, 1_013_000_000, 2)], sidecar_rows=rows(_packet(1, hidden, 1_003_000_000, 1), _packet(1, base, 1_013_000_000, 2)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_FAIL))
    cases.append(("dedup", evaluate_trace([_packet(0, base, 1_000_000_000, 0, "lo"), _packet(0, base, 1_001_000_000, 0, "lan")] + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_PASS))
    cases.append(("repeated_not_deduped", evaluate_trace([_packet(0, base, 1_000_000_000, 0, "lo"), _packet(0, base, 1_005_000_000, 0, "lo"), _packet(1, base, 1_002_000_000, 1), _packet(1, base, 1_007_000_000, 2)], sidecar_rows=rows(_packet(1, base, 1_002_000_000, 1), _packet(1, base, 1_007_000_000, 2)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_PASS))
    cases.append(("stale_sidecar", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1, stale=True), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_run_id_anchor", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), required_coverage={"scripted:script"}), VERDICT_INVALID))
    cases.append(("missing_sidecar_header_anchor", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), bridge_status=status, required_coverage={"scripted:script"}), VERDICT_INVALID))
    cases.append(("missing_status_anchor", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, required_coverage={"scripted:script"}), VERDICT_INVALID))
    cases.append(("top_level_status_anchor_ignored", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status={"run_id": run_id}, required_coverage={"scripted:script"}), VERDICT_INVALID))
    cases.append(("seq_gap", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, base, 1_010_000_000, 0), _packet(1, base, 1_002_000_000, 1), _packet(1, base, 1_012_000_000, 3)], sidecar_rows=rows(_packet(1, base, 1_002_000_000, 1), _packet(1, base, 1_012_000_000, 3)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("seq_wrap", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, base, 1_010_000_000, 0), _packet(1, base, 1_002_000_000, 255), _packet(1, base, 1_012_000_000, 1)], sidecar_rows=rows(_packet(1, base, 1_002_000_000, 255), _packet(1, base, 1_012_000_000, 1)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_PASS))
    cases.append(("seq_zero", evaluate_trace(u0 + [_packet(1, base, 1_003_000_000, 0)], sidecar_rows={}, sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    ambiguous_u1 = [_packet(1, base, 997_000_000, 1), _packet(1, base, 1_003_000_000, 2)]
    cases.append(("ambiguous_neighbor", evaluate_trace(u0 + ambiguous_u1, sidecar_rows=rows(*ambiguous_u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_u0", evaluate_trace(u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_u1", evaluate_trace(u0, sidecar_rows={}, sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_u1_frame", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, base, 1_010_000_000, 0), _packet(1, base, 1_003_000_000, 1)], sidecar_rows=rows(_packet(1, base, 1_003_000_000, 1)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("coverage_missing", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"scripted:script", "autoloop:x"}), VERDICT_INCOMPLETE))
    extra_u1 = _packet(1, base, 1_004_000_000, 2)
    cases.append(("extra_u1_frame", evaluate_trace(u0 + u1 + [extra_u1], sidecar_rows=rows(*u1, extra_u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("sidecar_unmatched_frame", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1, extra_u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("sidecar_frame_index", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], 999)], sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    idle_u0b = _packet(0, base, 1_010_000_000, 0)
    idle_u1b = _packet(1, base, 1_013_000_000, 2)
    idle_row_1 = row(u1[0], 1, scripted_active=False, active_deck=1)
    idle_row_2 = row(idle_u1b, 2, scripted_active=False, active_deck=2)
    cases.append(("idle_deck_transition", evaluate_trace(u0 + u1 + [idle_u0b, idle_u1b], sidecar_rows=[idle_row_1, idle_row_2], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"transition|deck|1->2"}), VERDICT_INCOMPLETE))
    base_idle_u0c = _packet(0, hidden, 1_020_000_000, 0)
    base_idle_u1c = _packet(1, hidden, 1_023_000_000, 3)
    cases.append(("base_idle_base_deck_transition", evaluate_trace(u0 + u1 + [idle_u0b, idle_u1b, base_idle_u0c, base_idle_u1c], sidecar_rows=[row(u1[0], 1, active_deck=1), idle_row_2, row(base_idle_u1c, 3, active_deck=1)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"transition|deck|2->1"}), VERDICT_INCOMPLETE))
    timeline_required = {
        "scripted:script",
        "scripted_start|script",
        "scripted_event|script|0:0:cue:a",
        "scripted_event|script|50:1:cue:b",
        "scripted_end|script",
        "scripted_rapid_pair|script|0:0:cue:a|50:1:cue:b",
    }
    u0b = _packet(0, hidden, 1_010_000_000, 0)
    u1b = _packet(1, hidden, 1_013_000_000, 2)
    cases.append(("scripted_timeline_missing", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], elapsed_ms=0)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage=timeline_required), VERDICT_INCOMPLETE))
    cases.append(("scripted_late_row_no_backfill", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], elapsed_ms=200)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage=timeline_required), VERDICT_INCOMPLETE))
    cases.append(("scripted_timeline_pass", evaluate_trace(u0 + u1 + [u0b, u1b], sidecar_rows=[row(u1[0], 1, elapsed_ms=0), row(u1b, 2, elapsed_ms=60)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage=timeline_required), VERDICT_PASS))
    cases.append(("failed_autoloop_no_coverage", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], scripted_active=False, soundswitch_id="", native_autoloop={"status": "missing_autoloop_file", "target_identity": "loop", "phase_tick": 100}, visible=True)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"autoloop:loop"}), VERDICT_INCOMPLETE))
    cases.append(("rapid_order", evaluate_trace([_packet(0, bytes([1]) + bytes(511), 1_000_000_000, 0), _packet(0, bytes([2]) + bytes(511), 1_046_875_000, 0), _packet(1, bytes([2]) + bytes(511), 1_003_000_000, 1), _packet(1, bytes([1]) + bytes(511), 1_049_000_000, 2)], sidecar_rows=rows(_packet(1, bytes([2]) + bytes(511), 1_003_000_000, 1), _packet(1, bytes([1]) + bytes(511), 1_049_000_000, 2)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_FAIL))
    bad = parse_artdmx(_build_artdmx(1, base, 1)[:-1], timestamp_ns=1_000_000_000)
    assert bad is not None
    cases.append(("packet_length", evaluate_trace(u0 + [bad], sidecar_rows={}, sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    partial_header, partial_rows, partial_invalid = parse_sidecar_jsonl(json.dumps({"type": "header", "run_id": run_id}) + "\n" + '{"type":"frame"')
    if partial_invalid:
        raise SystemExit("self-check failed: partial sidecar tail marked invalid")
    cases.append(("partial_sidecar", evaluate_trace(u0 + u1, sidecar_rows=partial_rows, sidecar_header=partial_header, bridge_status=status, sidecar_invalid=partial_invalid, sidecar_pending=True), VERDICT_INCOMPLETE))
    cases.append(("partial_sidecar_timeout", evaluate_trace(u0 + u1, sidecar_rows=partial_rows, sidecar_header=partial_header, bridge_status=status, sidecar_invalid=partial_invalid), VERDICT_INVALID))
    cases.append(("overload", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status, compare_overloaded=True), VERDICT_INVALID))

    failures = [(name, got.verdict, expected, got.reason) for name, got, expected in cases if got.verdict != expected]
    if failures:
        raise SystemExit("self-check failed: " + repr(failures))
    print(f"self-check PASS ({len(cases)} synthetic traces)")


def _load_status(path: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise RuntimeError(f"cannot read bridge status: {type(last_error).__name__ if last_error else 'invalid'}")


def _bind_sockets() -> list[socket.socket]:
    addresses = ["127.0.0.1"]
    lan = _detect_lan_ip()
    if lan not in addresses:
        addresses.append(lan)
    sockets: list[socket.socket] = []
    for address in addresses:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind((address, ARTNET_PORT))
            sock.setblocking(False)
            sockets.append(sock)
            print(f"bound {address}:{ARTNET_PORT}")
        except OSError as exc:
            sock.close()
            print(f"bind skipped {address}:{ARTNET_PORT} {type(exc).__name__}", file=sys.stderr)
    if not sockets:
        raise RuntimeError("no Art-Net sockets bound")
    return sockets


def _detect_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        return "127.0.0.1"


def _live(args: argparse.Namespace) -> int:
    if not args.pack_path:
        print("--pack-path is required outside --self-check", file=sys.stderr)
        return 2
    pack = load_pack(args.pack_path)
    required = build_coverage_ledger(pack)
    status = _load_status(args.bridge_status)
    status_pack_sha = str(status.get("soundswitch_pack", {}).get("pack_sha256") or "")
    pack_sha = str(getattr(pack, "manifest_sha256", "") or "")
    if status_pack_sha and pack_sha and status_pack_sha != pack_sha:
        print(json.dumps(CompareResult(VERDICT_INVALID, "pack_sha_mismatch", "SETUP_INVALID", remaining_coverage=tuple(sorted(required))).to_dict()))
        return 1
    truth = status.get("soundswitch_pack", {}).get("truth_check", {})
    sidecar_path = args.sidecar or (truth.get("sidecar_path") if isinstance(truth, dict) else "")
    sockets = _bind_sockets()
    packets: list[ArtDmxPacket] = []
    report_path = Path(args.report_out) if args.report_out else None
    try:
        start = time.monotonic()
        last_print = time.monotonic()
        while True:
            readable, _, _ = select.select(sockets, [], [], 0.25)
            for sock in readable:
                data, addr = sock.recvfrom(2048)
                packet = parse_artdmx(
                    data,
                    timestamp_ns=time.perf_counter_ns(),
                    source=f"{addr[0]}:{addr[1]}",
                    socket_name=sock.getsockname()[0],
                )
                if packet is not None:
                    packets.append(packet)
            if time.monotonic() - last_print >= 1.0:
                sidecar_header: dict[str, Any] | None = None
                sidecar_rows: list[dict[str, Any]] = []
                sidecar_invalid = not bool(sidecar_path)
                sidecar_pending = False
                elapsed = time.monotonic() - start
                if sidecar_path:
                    try:
                        sidecar_text = Path(sidecar_path).read_text(encoding="utf-8")
                        sidecar_pending = _has_partial_sidecar_tail(sidecar_text) and elapsed < args.timeout_s
                        sidecar_header, sidecar_rows, sidecar_invalid = parse_sidecar_jsonl(sidecar_text)
                    except OSError:
                        sidecar_invalid = True
                result = evaluate_trace(
                    packets,
                    ss_universe=args.ss_universe,
                    bridge_universe=args.bridge_universe,
                    sidecar_rows=sidecar_rows,
                    sidecar_header=sidecar_header,
                    bridge_status=status.get("soundswitch_pack", {}),
                    tolerance_ms=args.tolerance_ms,
                    required_coverage=required,
                    sidecar_invalid=sidecar_invalid,
                    sidecar_pending=sidecar_pending,
                )
                print(json.dumps(result.to_dict(), sort_keys=True))
                if report_path:
                    with report_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
                if result.reason in ("missing_u0", "missing_u1") and elapsed < args.timeout_s:
                    last_print = time.monotonic()
                    continue
                if result.verdict in (VERDICT_FAIL, VERDICT_INVALID, VERDICT_PASS):
                    return 0 if result.verdict == VERDICT_PASS else 1
                if elapsed >= args.timeout_s:
                    return 1
                last_print = time.monotonic()
    except KeyboardInterrupt:
        return 130
    finally:
        for sock in sockets:
            sock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="run synthetic validator self-checks and exit")
    parser.add_argument("--ss-universe", type=int, default=0)
    parser.add_argument("--bridge-universe", type=int, default=1)
    parser.add_argument("--pack-path")
    parser.add_argument("--bridge-status", default="/tmp/rb_ss_bridge_v2_status.json")
    parser.add_argument("--sidecar")
    parser.add_argument("--tolerance-ms", type=float, default=5.0)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--report-out")
    args = parser.parse_args(argv)
    if args.self_check:
        run_self_check()
        return 0
    return _live(args)


if __name__ == "__main__":
    raise SystemExit(main())
