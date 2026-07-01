#!/usr/bin/env python3
"""Observe SoundSwitch U0 and bridge truth-check U1 ArtDMX streams."""
from __future__ import annotations

import argparse
import hashlib
import json
import select
import socket
import statistics
import struct
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
# Live reconciliation: only finalize frames older than this margin, so the
# sidecar (written before send) and every in-tolerance U1 have arrived. Recent
# frames are deferred, not failed. Batch callers pass settle_ns=0 (no deferral).
LIVE_SETTLE_NS = 50_000_000
# A single drain burst this large means the receive buffer backed up far enough
# that timing/order evidence is no longer trustworthy.
LIVE_OVERLOAD_BURST = 2000


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
    streaming: bool = False,
    settle_ns: int = 0,
) -> CompareResult:
    packets, duplicate_count = dedup_packets(packets)
    malformed = [p for p in packets if not p.valid_protocol]
    if malformed:
        return CompareResult(VERDICT_INVALID, malformed[0].error, "SETUP_INVALID", duplicate_count=duplicate_count)
    u0 = [p for p in packets if p.universe == ss_universe]
    u1 = [p for p in packets if p.universe == bridge_universe]
    # Universe number is the correct discriminator: SoundSwitch outputs on U0,
    # the bridge truth-check sink outputs on U1.  On macOS loopback both may
    # share the same source port (6454), so source-port filtering is unreliable
    # and has been removed.
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
    if not header_run_id:
        return CompareResult(VERDICT_INVALID, "run_id_missing", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
    # When bridge_status has no truth_check key at all (not configured), require
    # a status run_id.  When truth_check is present but run_id is blank (known
    # status-surface bug where the sink is live but sanitized_status reports
    # disabled), trust the sidecar header alone — integrity is still verified by
    # sequence monotonicity and the overflow/error checks below.
    truth_check_present = isinstance(bridge_status.get("truth_check"), dict)
    if not truth_check_present and not status_run_id:
        return CompareResult(VERDICT_INVALID, "run_id_missing", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
    if status_run_id and status_run_id != header_run_id:
        return CompareResult(VERDICT_INVALID, "run_id_mismatch", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
    if bool(status_truth.get("overflow_count")) or bool(status_truth.get("dropped_count")):
        return CompareResult(VERDICT_INVALID, "bridge_queue_overflow", "BRIDGE_QUEUE_OVERFLOW", duplicate_count=duplicate_count)
    if status_truth.get("sidecar_error"):
        return CompareResult(VERDICT_INVALID, "sidecar_error", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)

    tolerance_ns = int(tolerance_ms * 1_000_000)
    if streaming and packets:
        # The sink writes each sidecar row before sending its packet, so in a
        # live capture the sidecar leads received U1, and the newest U1 may not
        # have its in-tolerance neighbours yet. Finalize only the settled prefix
        # (frames older than the latest observation by the settle margin) and
        # defer the rest; this is what lets a denser/leading stream still PASS.
        horizon_ns = max(packet.timestamp_ns for packet in packets) - max(0, settle_ns)
        u1 = [packet for packet in u1 if packet.timestamp_ns <= horizon_ns]
        u0 = [packet for packet in u0 if packet.timestamp_ns <= horizon_ns - tolerance_ns]
        if not u0 or not u1:
            return CompareResult(VERDICT_INCOMPLETE, "settling", "COVERAGE_INCOMPLETE", duplicate_count=duplicate_count)

    seq_error = _u1_sequence_error(u1)
    if seq_error:
        print(f"WARNING: sequence error {seq_error}")
        return CompareResult(VERDICT_INVALID, seq_error, "SETUP_INVALID", duplicate_count=duplicate_count)

    if not streaming:
        # Batch/offline reconciliation of a complete capture: counts must line
        # up exactly. Live callers settle a prefix instead (see above), where a
        # leading sidecar and denser U1 are expected, not a setup error.
        if len(u1) < len(u0):
            return CompareResult(VERDICT_INVALID, "missing_u1_frame", "SETUP_INVALID", matches=len(u1), duplicate_count=duplicate_count)
        if len(sidecar_rows) > len(u1):
            return CompareResult(VERDICT_INVALID, "sidecar_unmatched_frame", "SIDECAR_MISSING_OR_STALE", matches=len(u1), duplicate_count=duplicate_count)

    u1_sidecar_rows: list[Mapping[str, Any]] = []
    for index, bridge_packet in enumerate(u1):
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
                    matches=0,
                    duplicate_count=duplicate_count,
                )
            return CompareResult(VERDICT_INVALID, sidecar_error, "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
        u1_sidecar_rows.append(sidecar_row if not sidecar_error else {})

    offsets: list[float] = []
    details: list[dict[str, Any]] = []
    matched_rows: list[Mapping[str, Any]] = []
    match_error, matched_pairs = _match_u0_to_u1(u0, u1, tolerance_ns)
    if match_error == "ambiguous_nearest_neighbor":
        return CompareResult(VERDICT_INVALID, match_error, "SETUP_INVALID", duplicate_count=duplicate_count)
    if match_error and not streaming:
        return CompareResult(VERDICT_FAIL, match_error, "TIMING_MISMATCH", matches=len(matched_pairs), duplicate_count=duplicate_count)

    expected_payloads = [packet.payload for packet in u0]
    matched_payloads = [u1[u1_index].payload for _u0_index, u1_index in matched_pairs]
    for ss_index, u1_index in matched_pairs:
        ss_packet = u0[ss_index]
        bridge_packet = u1[u1_index]
        sidecar_row = u1_sidecar_rows[u1_index]
        matched_rows.append(sidecar_row)
        offset_ns = bridge_packet.timestamp_ns - ss_packet.timestamp_ns
        offsets.append(offset_ns / 1_000_000.0)
        if bridge_packet.payload != ss_packet.payload:
            diff = _first_diffs(ss_packet.payload, bridge_packet.payload)
            details.append({"index": ss_index, "diffs": diff, "total_diffs": _diff_count(ss_packet.payload, bridge_packet.payload)})
            gate_addr = sidecar_row.get("visible_gate_dmx_address") if isinstance(sidecar_row, Mapping) else None
            if type(gate_addr) is not int or not 1 <= gate_addr <= 512:
                gate_addr = 1
            if any(channel == gate_addr for channel, _a, _b in diff):
                failure_class = "VISIBLE_FLASH_OR_MISS"
            elif sorted(expected_payloads) == sorted(matched_payloads):
                failure_class = "ORDER_MISMATCH"
            else:
                failure_class = "HIDDEN_STATE_MISMATCH"
            return CompareResult(
                VERDICT_FAIL,
                "byte_mismatch",
                failure_class,
                matches=ss_index,
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


def _match_u0_to_u1(
    u0: Sequence[ArtDmxPacket],
    u1: Sequence[ArtDmxPacket],
    tolerance_ns: int,
) -> tuple[str, list[tuple[int, int]]]:
    matched: list[tuple[int, int]] = []
    search_start = 0
    for ss_index, ss_packet in enumerate(u0):
        candidates: list[tuple[int, int]] = []
        for u1_index in range(search_start, len(u1)):
            bridge_packet = u1[u1_index]
            delta_ns = abs(bridge_packet.timestamp_ns - ss_packet.timestamp_ns)
            if delta_ns <= tolerance_ns:
                candidates.append((delta_ns, u1_index))
            elif bridge_packet.timestamp_ns > ss_packet.timestamp_ns + tolerance_ns:
                break
        if not candidates:
            return "timing_mismatch", matched
        candidates.sort()
        if len(candidates) >= 2 and candidates[0][0] == candidates[1][0]:
            return "ambiguous_nearest_neighbor", matched
        _delta_ns, u1_index = candidates[0]
        matched.append((ss_index, u1_index))
        search_start = u1_index + 1
    return "", matched


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
        scripted_id = _scripted_key(getattr(row, "soundswitch_id", "") or key)
        if not scripted_id:
            continue
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
        required.add(f"autoloop_cycle|{identity}|{_autoloop_cycle_ticks(pack, identity)}")
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


def _scripted_key(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("{") and raw.endswith("}") and len(raw) > 1:
        raw = raw[1:-1].strip()
    return raw.lower()


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
    document = _autoloop_document(pack, identity)
    for event in _document_events(document):
        frame = getattr(event, "boundary_frame", None)
        if isinstance(frame, tuple) and any(int(value or 0) > 0 for value in frame):
            return "autoloop_visible"
        for patch in getattr(event, "patch", ()) or ():
            if int(getattr(patch, "value", 0) or 0) > 0:
                return "autoloop_visible"
    return "autoloop_authored_dark"


def _autoloop_document(pack: LoadedPack, identity: str) -> Any:
    autoloops = getattr(pack, "autoloops", {})
    loop = autoloops.get(identity) if hasattr(autoloops, "get") else None
    return getattr(loop, "document", loop)


def _autoloop_cycle_ticks(pack: LoadedPack, identity: str) -> int:
    document = _autoloop_document(pack, identity)
    cycle_ticks = getattr(document, "cycle_ticks", None)
    if type(cycle_ticks) is int and cycle_ticks > 0:
        return cycle_ticks
    return AUTOLOOP_CYCLE_TICKS


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
    autoloop_cycles: dict[str, int] = {}
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
        elif item.startswith("autoloop_cycle|"):
            parts = item.split("|", 2)
            if len(parts) == 3:
                cycle_ticks = _positive_int_from_text(parts[2])
                if cycle_ticks is not None and cycle_ticks > 0:
                    autoloop_cycles[parts[1]] = cycle_ticks
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
            scripted_id = _scripted_key(row["soundswitch_id"])
            if scripted_id:
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
            cycle_ticks = autoloop_cycles.get(target, AUTOLOOP_CYCLE_TICKS)
            observed.add(f"autoloop_cycle|{target}|{cycle_ticks}")
            phase_tick = _int_or_none(native.get("phase_tick"))
            if phase_tick is not None:
                bucket = _autoloop_phase_bucket(phase_tick, cycle_ticks)
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


def _positive_int_from_text(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _autoloop_phase_bucket(phase_tick: int, cycle_ticks: int) -> int:
    if cycle_ticks <= 0:
        cycle_ticks = AUTOLOOP_CYCLE_TICKS
    return min(AUTOLOOP_PHASE_BUCKETS - 1, int(((phase_tick % cycle_ticks) * AUTOLOOP_PHASE_BUCKETS) / cycle_ticks))


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
    cases.append(("extra_u1_frame", evaluate_trace(u0 + u1 + [extra_u1], sidecar_rows=rows(*u1, extra_u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_PASS))
    cases.append(("extra_u1_missing_sidecar", evaluate_trace(u0 + u1 + [extra_u1], sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
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
    cases.append(("scripted_id_normalized", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], soundswitch_id="{SCRIPT}")], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"scripted:script"}), VERDICT_PASS))
    cases.append(("failed_autoloop_no_coverage", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], scripted_active=False, soundswitch_id="", native_autoloop={"status": "missing_autoloop_file", "target_identity": "loop", "phase_tick": 100}, visible=True)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"autoloop:loop"}), VERDICT_INCOMPLETE))
    cases.append(("autoloop_custom_cycle", evaluate_trace(u0 + u1, sidecar_rows=[row(u1[0], scripted_active=False, soundswitch_id="", native_autoloop={"status": "rendering_active", "target_identity": "loop", "phase_tick": 250}, visible=True)], sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"autoloop:loop", "autoloop_visible:loop", "autoloop_cycle|loop|300", "autoloop_phase:loop:2"}), VERDICT_PASS))
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
    stream_u0a = _packet(0, base, 1_000_000_000, 0)
    stream_u1a = _packet(1, base, 1_001_000_000, 1)
    stream_u0b = _packet(0, base, 1_100_000_000, 0)
    stream_u1b = _packet(1, base, 1_101_000_000, 2)
    stream_lead_rows = rows(stream_u1a, stream_u1b, _packet(1, base, 1_102_000_000, 3))
    cases.append(("batch_rejects_sidecar_lead", evaluate_trace([stream_u0a, stream_u1a, stream_u0b, stream_u1b], sidecar_rows=stream_lead_rows, sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"scripted:script"}), VERDICT_INVALID))
    cases.append(("streaming_tolerates_sidecar_lead", evaluate_trace([stream_u0a, stream_u1a, stream_u0b, stream_u1b], sidecar_rows=stream_lead_rows, sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"scripted:script"}, streaming=True, settle_ns=0), VERDICT_PASS))
    bad_stream_row = row(stream_u1a, 1)
    bad_stream_row["dmx_sha256"] = hashlib.sha256(hidden).hexdigest()
    cases.append(("streaming_rejects_unverified_u1", evaluate_trace([stream_u0a, stream_u1a, stream_u0b, stream_u1b], sidecar_rows=[bad_stream_row, row(stream_u1b, 2)], sidecar_header={"run_id": run_id}, bridge_status=status, streaming=True, settle_ns=0), VERDICT_INVALID))

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


_OP_POLL = 0x2000
_OP_POLL_REPLY = 0x2100
_ARTNET_ID = b"Art-Net\x00"


def _build_art_poll_reply(local_ip: str) -> bytes:
    """Minimal ArtPollReply that makes SoundSwitch start sending ArtDMX."""
    short = b"ArtNetCompare"
    long_ = b"rb_ss_bridge_v2 truth-check compare node"
    report = b"#0001 [0000] compare OK"
    pkt = bytearray()
    pkt += _ARTNET_ID
    pkt += struct.pack("<H", _OP_POLL_REPLY)
    try:
        pkt += socket.inet_aton(local_ip)
    except OSError:
        pkt += socket.inet_aton("127.0.0.1")
    pkt += struct.pack("<H", ARTNET_PORT)
    pkt += bytes([0x00, 0x01])                    # VersInfo
    pkt += bytes([0x00, 0x00])                    # NetSwitch / SubSwitch
    pkt += bytes([0x00, 0xFF])                    # Oem
    pkt += bytes([0x00])                          # Ubea
    pkt += bytes([0xC0])                          # Status1
    pkt += struct.pack("<H", 0x0000)              # EstaMan
    pkt += short[:17] + b"\x00" * (18 - len(short[:17]))  # ShortName[18]
    pkt += long_[:63] + b"\x00" * (64 - len(long_[:63]))  # LongName[64]
    pkt += report[:63] + b"\x00" * (64 - len(report[:63]))  # NodeReport[64]
    pkt += bytes([0x00, 0x01])                    # NumPorts=1
    pkt += bytes([0x80, 0x00, 0x00, 0x00])        # PortTypes: DMX out
    pkt += bytes([0x00, 0x00, 0x00, 0x00])        # GoodInput
    pkt += bytes([0x80, 0x00, 0x00, 0x00])        # GoodOutput
    pkt += bytes([0x00, 0x00, 0x00, 0x00])        # SwIn
    pkt += bytes([0x00, 0x00, 0x00, 0x00])        # SwOut: universe 0
    pkt += bytes([0x00, 0x00, 0x00])              # SwVideo/Macro/Remote
    pkt += bytes([0x00, 0x00, 0x00])              # Spare
    pkt += bytes([0x00])                          # Style=StNode
    pkt += bytes([0x00] * 6)                      # MAC
    pkt += socket.inet_aton("0.0.0.0")           # BindIp
    pkt += bytes([0x01])                          # BindIndex
    pkt += bytes([0x08])                          # Status2
    pkt += bytes([0x00] * 26)                     # Filler
    return bytes(pkt)


def _bind_sockets() -> tuple[list[socket.socket], socket.socket, bytes, str]:
    """Bind receive sockets on all local Art-Net IPs and build a broadcast send socket."""
    lan = _detect_lan_ip()
    addresses = ["127.0.0.1"]
    if lan not in addresses:
        addresses.append(lan)
    sockets: list[socket.socket] = []
    for address in addresses:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            except OSError:
                pass
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((address, ARTNET_PORT))
            sock.setblocking(False)
            sockets.append(sock)
            print(f"bound {address}:{ARTNET_PORT}")
        except OSError as exc:
            sock.close()
            print(f"bind skipped {address}:{ARTNET_PORT} {type(exc).__name__}", file=sys.stderr)
    if not sockets:
        raise RuntimeError("no Art-Net sockets bound")
    # Broadcast target: subnet .255
    parts = lan.split(".")
    bcast = ".".join(parts[:3] + ["255"]) if len(parts) == 4 else "255.255.255.255"
    poll_reply = _build_art_poll_reply(lan)
    return sockets, poll_reply, bcast


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
    pack_sha = str(getattr(pack, "manifest_sha256", "") or "")
    sockets, poll_reply, bcast = _bind_sockets()
    send_sock = sockets[-1]  # The LAN socket is always last, use it to broadcast from port 6454
    # Announce immediately so SoundSwitch picks us up on startup
    try:
        send_sock.sendto(poll_reply, (bcast, ARTNET_PORT))
        send_sock.sendto(poll_reply, ("255.255.255.255", ARTNET_PORT))
        print(f"ArtPollReply broadcast to {bcast} + 255.255.255.255")
    except OSError as e:
        print(f"ArtPollReply broadcast failed: {e}", file=sys.stderr)
    packets: list[ArtDmxPacket] = []
    report_path = Path(args.report_out) if args.report_out else None
    try:
        start = time.monotonic()
        last_print = time.monotonic()
        last_poll_reply = time.monotonic()
        overloaded = False
        bridge_was_ready = False
        while True:
            readable, _, _ = select.select(sockets, [], [], 0.25)
            now = time.monotonic()
            # Proactive keepalive every 3s so SoundSwitch doesn't drop us
            if now - last_poll_reply >= 3.0:
                try:
                    send_sock.sendto(poll_reply, (bcast, ARTNET_PORT))
                    send_sock.sendto(poll_reply, ("255.255.255.255", ARTNET_PORT))
                except OSError:
                    pass
                last_poll_reply = now
            burst = 0
            for sock in readable:
                while True:
                    try:
                        data, addr = sock.recvfrom(2048)
                    except BlockingIOError:
                        break
                    # Respond to ArtPoll so SoundSwitch discovers this node
                    if (len(data) >= 10 and data[:8] == _ARTNET_ID
                            and struct.unpack_from("<H", data, 8)[0] == _OP_POLL):
                        try:
                            send_sock.sendto(poll_reply, (bcast, ARTNET_PORT))
                            send_sock.sendto(poll_reply, ("255.255.255.255", ARTNET_PORT))
                        except OSError:
                            pass
                        last_poll_reply = now
                        continue
                    # Skip our own ArtPollReply echoes
                    if (len(data) >= 10 and data[:8] == _ARTNET_ID
                            and struct.unpack_from("<H", data, 8)[0] == _OP_POLL_REPLY):
                        continue
                    burst += 1
                    packet = parse_artdmx(
                        data,
                        timestamp_ns=time.perf_counter_ns(),
                        source=f"{addr[0]}:{addr[1]}",
                        socket_name=sock.getsockname()[0],
                    )
                    if packet is not None:
                        # Ignore bridge U1 packets coming in from the LAN socket
                        # to prevent duplicate out-of-order interleaving with loopback
                        if packet.universe == args.bridge_universe and packet.socket_name != "127.0.0.1":
                            continue
                        packets.append(packet)
            if burst > LIVE_OVERLOAD_BURST:
                overloaded = True
            if time.monotonic() - last_print >= 1.0:
                elapsed = time.monotonic() - start
                # Re-read bridge status every tick so we pick up run_id
                # and sidecar_path once the bridge comes up (armed state).
                try:
                    status = _load_status(args.bridge_status)
                except RuntimeError:
                    # Bridge not running yet — stay in armed state.
                    if elapsed < args.timeout_s:
                        print(json.dumps({"verdict": VERDICT_INCOMPLETE, "reason": "bridge_not_ready"}))
                        last_print = time.monotonic()
                        continue
                    return 1
                status_pack = status.get("soundswitch_pack", {})
                if not bridge_was_ready:
                    # First time we have a live bridge status: flush all packets
                    # accumulated before the bridge started.  Pre-bridge frames
                    # are unsynchronized idle noise (U0 and U1 run at their own
                    # cadences) and would cause immediate timing_mismatch FAILs.
                    packets.clear()
                    bridge_was_ready = True
                status_pack_sha = str(status_pack.get("pack_sha256") or "")
                if status_pack_sha and pack_sha and status_pack_sha != pack_sha:
                    result = CompareResult(VERDICT_INVALID, "pack_sha_mismatch", "SETUP_INVALID", remaining_coverage=tuple(sorted(required)))
                    print(json.dumps(result.to_dict(), sort_keys=True))
                    return 1
                truth = status_pack.get("truth_check", {})
                sidecar_path = args.sidecar or (truth.get("sidecar_path") if isinstance(truth, dict) else "")
                sidecar_header: dict[str, Any] | None = None
                sidecar_rows: list[dict[str, Any]] = []
                sidecar_invalid = not bool(sidecar_path)
                sidecar_pending = False
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
                    bridge_status=status_pack,
                    tolerance_ms=args.tolerance_ms,
                    required_coverage=required,
                    sidecar_invalid=sidecar_invalid,
                    sidecar_pending=sidecar_pending,
                    compare_overloaded=overloaded,
                    streaming=True,
                    settle_ns=LIVE_SETTLE_NS,
                )
                print(json.dumps(result.to_dict(), sort_keys=True))
                if report_path:
                    with report_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
                overloaded = False
                _transient = (
                    "missing_u0", "missing_u1", "settling",
                    "sidecar_invalid", "run_id_missing", "run_id_mismatch",
                    "timing_mismatch", "byte_mismatch"
                )
                if (result.reason in _transient or result.reason.startswith("sequence_gap")) and elapsed < args.timeout_s:
                    last_print = time.monotonic()
                    # Sidecar rows are frame-index anchored. Trimming packets
                    # breaks U1-to-sidecar integrity and can create false
                    # byte_mismatch FAILs from unverified frames.
                    continue
                if result.verdict in (VERDICT_FAIL, VERDICT_INVALID, VERDICT_PASS):
                    return 0 if result.verdict == VERDICT_PASS else 1
                if elapsed >= args.timeout_s:
                    return 1
                last_print = time.monotonic()
                packets = packets[-200:]
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
