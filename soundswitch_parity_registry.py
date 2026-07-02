"""Computed SoundSwitch parity lane helpers."""
from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping

ParityLane = Literal["oracle_proven", "algorithm_generalized", "unverified_parity"]
PARITY_LANES = frozenset(("oracle_proven", "algorithm_generalized", "unverified_parity"))


def classify_parity_lane(
    *,
    structural_supported: bool,
    oracle_report: Mapping[str, Any] | None = None,
    generalized_witness_passed: bool = False,
) -> ParityLane:
    """Classify from evidence only; never from document identity."""
    if oracle_report and oracle_report.get("verdict") == "PASS" \
            and oracle_report.get("truth_source") == "SoundSwitch U0":
        return "oracle_proven"
    if structural_supported and generalized_witness_passed:
        return "algorithm_generalized"
    return "unverified_parity"


def parity_evidence(
    *,
    lane: ParityLane,
    reason: str,
    structural_supported: bool,
    capture_id: str = "",
    oracle_report_sha256: str = "",
) -> dict[str, Any]:
    return {
        "capture_id": capture_id,
        "oracle_report_sha256": oracle_report_sha256,
        "reason": reason,
        "structural_supported": bool(structural_supported),
        "truth_source": "SoundSwitch U0" if lane == "oracle_proven" else "",
    }


def count_lanes(lanes: list[str]) -> dict[str, int]:
    counts = {lane: 0 for lane in sorted(PARITY_LANES)}
    for lane in lanes:
        counts[lane if lane in PARITY_LANES else "unverified_parity"] += 1
    return counts


def generalized_witness_passed(
    registry_docs: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    layout: str,
    document_fully_resolved: bool,
) -> bool:
    if not document_fully_resolved:
        return False
    rows = registry_docs.values() if isinstance(registry_docs, Mapping) else registry_docs
    return any(
        row.get("layout") == layout
        and row.get("verdict") == "PASS"
        and row.get("truth_source", "SoundSwitch U0") == "SoundSwitch U0"
        for row in rows
    )


__all__ = [
    "PARITY_LANES", "ParityLane", "classify_parity_lane", "count_lanes",
    "generalized_witness_passed", "parity_evidence",
]
