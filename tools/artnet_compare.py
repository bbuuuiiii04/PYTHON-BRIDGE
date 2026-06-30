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
from typing import Any, Iterable, Mapping

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


def parse_sidecar_jsonl(text: str) -> tuple[dict[str, Any] | None, dict[int, dict[str, Any]], bool]:
    header: dict[str, Any] | None = None
    rows: dict[int, dict[str, Any]] = {}
    invalid = False
    for raw in text.splitlines(keepends=True):
        if not raw.endswith("\n"):
            if raw.strip():
                invalid = True
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
            seq = row.get("sequence")
            if type(seq) is int:
                rows[seq] = row
    return header, rows, invalid


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
    sidecar_rows: Mapping[int, Mapping[str, Any]] | None = None,
    sidecar_header: Mapping[str, Any] | None = None,
    bridge_status: Mapping[str, Any] | None = None,
    tolerance_ms: float = 5.0,
    required_coverage: Iterable[str] = (),
    sidecar_invalid: bool = False,
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

    sidecar_rows = sidecar_rows or {}
    bridge_status = bridge_status or {}
    status_truth = bridge_status.get("truth_check") if isinstance(bridge_status.get("truth_check"), dict) else {}
    status_run_id = str(status_truth.get("run_id") or bridge_status.get("run_id") or "")
    header_run_id = str((sidecar_header or {}).get("run_id") or "")
    if status_run_id and header_run_id and status_run_id != header_run_id:
        return CompareResult(VERDICT_INVALID, "run_id_mismatch", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)
    if bool(status_truth.get("overflow_count")) or bool(status_truth.get("dropped_count")):
        return CompareResult(VERDICT_INVALID, "bridge_queue_overflow", "BRIDGE_QUEUE_OVERFLOW", duplicate_count=duplicate_count)
    if status_truth.get("sidecar_error"):
        return CompareResult(VERDICT_INVALID, "sidecar_error", "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)

    seq_error = _u1_sequence_error(u1)
    if seq_error:
        return CompareResult(VERDICT_INVALID, seq_error, "U1_SEQUENCE_GAP", duplicate_count=duplicate_count)
    sidecar_error = _sidecar_error(u1, sidecar_rows, status_run_id or header_run_id)
    if sidecar_error:
        return CompareResult(VERDICT_INVALID, sidecar_error, "SIDECAR_MISSING_OR_STALE", duplicate_count=duplicate_count)

    if _ambiguous_nearest_neighbor(u0, u1, int(tolerance_ms * 1_000_000)):
        return CompareResult(VERDICT_INVALID, "ambiguous_nearest_neighbor", "SETUP_INVALID", duplicate_count=duplicate_count)

    if len(u1) < len(u0):
        return CompareResult(VERDICT_INVALID, "missing_u1_frame", "SETUP_INVALID", matches=len(u1), duplicate_count=duplicate_count)

    offsets: list[float] = []
    details: list[dict[str, Any]] = []
    tolerance_ns = int(tolerance_ms * 1_000_000)
    for index, ss_packet in enumerate(u0):
        bridge_packet = u1[index]
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

    observed = _observed_coverage(sidecar_rows.values())
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


def _sidecar_error(
    u1: list[ArtDmxPacket],
    rows: Mapping[int, Mapping[str, Any]],
    run_id: str,
) -> str:
    for packet in u1:
        row = rows.get(packet.sequence)
        if row is None:
            return f"sidecar_missing:{packet.sequence}"
        if run_id and str(row.get("run_id") or "") != run_id:
            return f"sidecar_run_id_mismatch:{packet.sequence}"
        expected_hash = hashlib.sha256(packet.payload).hexdigest()
        if row.get("dmx_sha256") != expected_hash:
            return f"sidecar_hash_mismatch:{packet.sequence}"
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
    for key, row in getattr(pack, "scripted", {}).items():
        supported = bool(getattr(row, "supported_active", True))
        if supported:
            required.add(f"scripted:{key}")
    for binding in getattr(pack, "autoloop_bindings", {}).values():
        required.add(f"autoloop:{binding.target_identity}")
    for binding in getattr(pack, "learned_midi_bindings", ()):
        if binding.target_kind == "static_look" and binding.target_slot is not None:
            required.add(f"static:{binding.target_slot}")
        elif binding.target_kind == "blackout_mask":
            required.add(f"blackout:{binding.channel_zero_based}:{binding.data_byte}")
    return required


def _observed_coverage(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    observed: set[str] = set()
    for row in rows:
        if row.get("scripted_active") and row.get("soundswitch_id"):
            observed.add(f"scripted:{row['soundswitch_id']}")
        native = row.get("native_autoloop") if isinstance(row.get("native_autoloop"), dict) else {}
        target = native.get("target_identity") if isinstance(native, dict) else ""
        if target:
            observed.add(f"autoloop:{target}")
        for slot in row.get("static_slots") or ():
            observed.add(f"static:{slot}")
        if row.get("blackout"):
            observed.add("blackout:observed")
    return observed


def _packet(universe: int, payload: bytes, timestamp_ns: int, sequence: int = 1, socket_name: str = "lo") -> ArtDmxPacket:
    parsed = parse_artdmx(_build_artdmx(universe, payload, sequence), timestamp_ns=timestamp_ns, socket_name=socket_name)
    assert parsed is not None
    return parsed


def run_self_check() -> None:
    base = bytes([7]) + bytes(511)
    hidden = bytes([0, 99]) + bytes(510)
    run_id = "selfcheck"

    def rows(*packets: ArtDmxPacket, stale: bool = False) -> dict[int, dict[str, Any]]:
        return {
            packet.sequence: {
                "type": "frame",
                "run_id": "old" if stale else run_id,
                "sequence": packet.sequence,
                "dmx_sha256": hashlib.sha256(packet.payload).hexdigest(),
                "scripted_active": True,
                "soundswitch_id": "script",
            }
            for packet in packets
        }

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
    cases.append(("seq_gap", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, base, 1_010_000_000, 0), _packet(1, base, 1_002_000_000, 1), _packet(1, base, 1_012_000_000, 3)], sidecar_rows=rows(_packet(1, base, 1_002_000_000, 1), _packet(1, base, 1_012_000_000, 3)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("seq_wrap", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, base, 1_010_000_000, 0), _packet(1, base, 1_002_000_000, 255), _packet(1, base, 1_012_000_000, 1)], sidecar_rows=rows(_packet(1, base, 1_002_000_000, 255), _packet(1, base, 1_012_000_000, 1)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_PASS))
    cases.append(("seq_zero", evaluate_trace(u0 + [_packet(1, base, 1_003_000_000, 0)], sidecar_rows={}, sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    ambiguous_u1 = [_packet(1, base, 997_000_000, 1), _packet(1, base, 1_003_000_000, 2)]
    cases.append(("ambiguous_neighbor", evaluate_trace(u0 + ambiguous_u1, sidecar_rows=rows(*ambiguous_u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_u0", evaluate_trace(u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_u1", evaluate_trace(u0, sidecar_rows={}, sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("missing_u1_frame", evaluate_trace([_packet(0, base, 1_000_000_000, 0), _packet(0, base, 1_010_000_000, 0), _packet(1, base, 1_003_000_000, 1)], sidecar_rows=rows(_packet(1, base, 1_003_000_000, 1)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    cases.append(("coverage_missing", evaluate_trace(u0 + u1, sidecar_rows=rows(*u1), sidecar_header={"run_id": run_id}, bridge_status=status, required_coverage={"scripted:script", "autoloop:x"}), VERDICT_INCOMPLETE))
    cases.append(("rapid_order", evaluate_trace([_packet(0, bytes([1]) + bytes(511), 1_000_000_000, 0), _packet(0, bytes([2]) + bytes(511), 1_046_875_000, 0), _packet(1, bytes([2]) + bytes(511), 1_003_000_000, 1), _packet(1, bytes([1]) + bytes(511), 1_049_000_000, 2)], sidecar_rows=rows(_packet(1, bytes([2]) + bytes(511), 1_003_000_000, 1), _packet(1, bytes([1]) + bytes(511), 1_049_000_000, 2)), sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_FAIL))
    bad = parse_artdmx(_build_artdmx(1, base, 1)[:-1], timestamp_ns=1_000_000_000)
    assert bad is not None
    cases.append(("packet_length", evaluate_trace(u0 + [bad], sidecar_rows={}, sidecar_header={"run_id": run_id}, bridge_status=status), VERDICT_INVALID))
    partial_header, partial_rows, partial_invalid = parse_sidecar_jsonl(json.dumps({"type": "header", "run_id": run_id}) + "\n" + '{"type":"frame"')
    cases.append(("partial_sidecar", evaluate_trace(u0 + u1, sidecar_rows=partial_rows, sidecar_header=partial_header, bridge_status=status, sidecar_invalid=partial_invalid), VERDICT_INVALID))
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
                sidecar_rows: dict[int, dict[str, Any]] = {}
                sidecar_invalid = not bool(sidecar_path)
                if sidecar_path:
                    try:
                        sidecar_header, sidecar_rows, sidecar_invalid = parse_sidecar_jsonl(
                            Path(sidecar_path).read_text(encoding="utf-8")
                        )
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
                )
                print(json.dumps(result.to_dict(), sort_keys=True))
                if report_path:
                    with report_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
                elapsed = time.monotonic() - start
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
