"""Frozen dataclasses + validators for every pilot artifact row (spec B3, B4, B7).

Each schema is a frozen dataclass. ``from_dict`` is strict: it rejects unknown
keys and missing keys, and ``__post_init__`` rejects out-of-domain enums and
nonfinite floats. That is the whole point of test D1 (schema rejection).
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "spectral-pilot-row-v1"

# --- enum domains (spec B3 §220, B6, B7, B8) ---------------------------------
SPLIT_ROLE = frozenset({"pilot", "development", "anchor"})
LINEAGE_REVIEW_STATE = frozenset({"confirmed", "unresolved"})
CURATOR_CONFIRMATION = frozenset(
    {"confirmed_related", "confirmed_unrelated", "unresolved", "not_applicable"}
)
EXCLUSION_REASON = frozenset(
    {
        "none", "development_overlap", "scripted", "missing_v4", "invalid_v4",
        "insufficient_markers", "unresolved_duplicate", "unresolved_lineage",
        "cross_partition_related", "pool_cap",
    }
)
CARD_TYPE = frozenset(
    {"anchor_confirm", "marker_state", "hardness_pair", "family_montage",
     "marker_repeat", "family_repeat"}
)
SESSION_INDEX = frozenset({"A", "P1", "P2", "P3"})
# Committed human answers (canonical forms; pair answers stored marker-relative).
MARKER_STATE_ANSWER = frozenset({"genuine", "not_genuine", "marker_wrong_or_ambiguous", "unsure"})
HARDNESS_ANSWER = frozenset({"harder", "tied", "softer", "unsure"})
FAMILY_ANSWER = frozenset({"WALL", "COMET", "HOUSE", "mixed", "none", "unsure"})
ANCHOR_CONFIRM_ANSWER = frozenset({"confirm", "reject"})
# Which of a card's questions a response answers (spec B7 amended).
QUESTION = frozenset({"anchor", "state", "hardness", "family"})
ANCHOR_ROLE = frozenset(
    {"WALL", "COMET", "HOUSE", "mixed", "T1", "T2", "T3"}
)
AXIS = frozenset({"genuine", "hardness", "family"})
GATE_STATE = frozenset({"PASS", "FAIL", "INCONCLUSIVE"})


def _check_enum(val: Any, domain: frozenset, name: str) -> None:
    if val not in domain:
        raise ValueError(f"{name}={val!r} not in {sorted(domain)}")


def _check_finite(val: Any, name: str) -> None:
    if isinstance(val, float) and not math.isfinite(val):
        raise ValueError(f"{name} is nonfinite: {val!r}")
    if type(val) not in (int, float, bool):  # exact-type: reject numpy scalars
        return
    # bool is fine; numpy int/float have non-builtin types and are rejected above.


def strict_from_dict(cls, d: dict):
    """Build ``cls`` from ``d`` rejecting unknown or missing fields (D1)."""
    if not isinstance(d, dict):
        raise TypeError(f"{cls.__name__}.from_dict expects a dict, got {type(d)!r}")
    names = {f.name for f in dataclasses.fields(cls)}
    extra = set(d) - names
    if extra:
        raise ValueError(f"unknown fields for {cls.__name__}: {sorted(extra)}")
    missing = names - set(d)
    if missing:
        raise ValueError(f"missing fields for {cls.__name__}: {sorted(missing)}")
    return cls(**d)


def _reject_numpy(values, where: str) -> None:
    for v in values:
        t = type(v)
        if t not in (int, float, str, bool, type(None), list, dict, tuple):
            raise TypeError(f"non-canonical value in {where}: {t!r}")


@dataclass(frozen=True)
class SelectedRow:
    """Seed-pool and selected-row schema (spec B3 §210, verbatim field set)."""
    schema_version: str
    pilot_seed: str
    created_from_head: str
    track_instance_id: str
    content_id_locator: str
    audio_sha256: str
    audio_duplicate_group: str
    recording_lineage_id: str
    split_role: str
    beatgrid_fingerprint: str
    marker_set_fingerprint: str
    label_store_hash: str
    exclusion_reason: str
    lineage_review_state: str
    curator_confirmation: str
    family_montage_marker_ids: list

    def __post_init__(self):
        _check_enum(self.split_role, SPLIT_ROLE, "split_role")
        _check_enum(self.exclusion_reason, EXCLUSION_REASON, "exclusion_reason")
        _check_enum(self.lineage_review_state, LINEAGE_REVIEW_STATE, "lineage_review_state")
        _check_enum(self.curator_confirmation, CURATOR_CONFIRMATION, "curator_confirmation")
        if not isinstance(self.family_montage_marker_ids, list):
            raise TypeError("family_montage_marker_ids must be a list")

    @classmethod
    def from_dict(cls, d: dict) -> "SelectedRow":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class CardManifestRow:
    """card_manifest.jsonl row (spec B7)."""
    schema_version: str
    pilot_seed: str
    card_id: str
    card_type: str
    session_index: str
    order_index: int
    track_instance_id: str
    marker_beat: Optional[int]
    display_left_id: Optional[str]
    display_right_id: Optional[str]
    anchor_role: Optional[str]
    repeat_of_card_id: Optional[str]
    clip_spec: dict
    card_hash: str

    def __post_init__(self):
        _check_enum(self.card_type, CARD_TYPE, "card_type")
        _check_enum(self.session_index, SESSION_INDEX, "session_index")
        if self.anchor_role is not None:
            _check_enum(self.anchor_role, ANCHOR_ROLE, "anchor_role")
        if not isinstance(self.order_index, int) or isinstance(self.order_index, bool):
            raise TypeError("order_index must be int")
        if not isinstance(self.clip_spec, dict):
            raise TypeError("clip_spec must be a dict")

    @classmethod
    def from_dict(cls, d: dict) -> "CardManifestRow":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ResponseRow:
    """responses.jsonl append-only row (spec B7, amended: question + local_date)."""
    schema_version: str
    pilot_seed: str
    card_id: str
    commit_index: int
    question: str
    displayed_response: str
    canonical_response: str
    recognized: bool
    response_seconds: float
    commit_utc: str
    local_date: str
    session_index: str
    segment_index: int
    prev_row_hash: str
    card_manifest_hash: str

    def __post_init__(self):
        _check_enum(self.session_index, SESSION_INDEX, "session_index")
        _check_enum(self.question, QUESTION, "question")
        if not isinstance(self.recognized, bool):
            raise TypeError("recognized must be bool")
        _check_finite(self.response_seconds, "response_seconds")
        if not math.isfinite(float(self.response_seconds)):
            raise ValueError("response_seconds must be finite")
        if self.response_seconds < 0:
            raise ValueError("response_seconds must be >= 0")

    @classmethod
    def from_dict(cls, d: dict) -> "ResponseRow":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class CandidateContract:
    """candidate_contracts.json per-method row (spec B7)."""
    schema_version: str
    pilot_seed: str
    method_version: str
    positive_allowlist: list
    scaler_population_hash: str
    retained_field_hash: str
    code_hash: str
    environment_lock_hash: str
    development_manifest_hash: str

    def __post_init__(self):
        if not isinstance(self.positive_allowlist, list):
            raise TypeError("positive_allowlist must be a list")

    @classmethod
    def from_dict(cls, d: dict) -> "CandidateContract":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class PredictionRow:
    """predictions/<method>.jsonl row (spec B4). No timing/RSS fields — telemetry
    lives only in resource_report.json, so this hash is deterministic."""
    schema_version: str
    pilot_seed: str
    method_version: str
    axis: str
    target_id: str
    manifest_hash: str
    input_hash: str
    scaler_population_hash: str
    eligible_neighbour_ids: list
    excluded_neighbour_ids: list
    distances: list
    prediction: Optional[str]
    abstained: bool
    raw_score: Optional[float]
    reason_codes: list
    error_state: Optional[str]

    def __post_init__(self):
        _check_enum(self.axis, AXIS, "axis")
        if not isinstance(self.abstained, bool):
            raise TypeError("abstained must be bool")
        if self.raw_score is not None:
            _check_finite(self.raw_score, "raw_score")
            if not math.isfinite(float(self.raw_score)):
                raise ValueError("raw_score must be finite when present")
        for name in ("eligible_neighbour_ids", "excluded_neighbour_ids", "distances", "reason_codes"):
            if not isinstance(getattr(self, name), list):
                raise TypeError(f"{name} must be a list")
        _reject_numpy(self.distances, "PredictionRow.distances")

    @classmethod
    def from_dict(cls, d: dict) -> "PredictionRow":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class PredictionHashes:
    """prediction_hashes.json (spec B7)."""
    schema_version: str
    pilot_seed: str
    method_hashes: dict
    card_manifest_hash: str
    lineage_manifest_hash: str
    freeze_utc: str

    def __post_init__(self):
        if not isinstance(self.method_hashes, dict):
            raise TypeError("method_hashes must be a dict")

    @classmethod
    def from_dict(cls, d: dict) -> "PredictionHashes":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ResourceReport:
    """resource_report.json (spec B7). Telemetry only — never hashed into verdict."""
    schema_version: str
    pilot_seed: str
    analysis_wall_seconds: float
    peak_rss_bytes: int
    scratch_peak_bytes: int
    retained_bytes: int
    manual_prep_minutes: float
    human_active_seconds: float
    decisions_total: int
    cleanup_seconds: float
    ceilings: dict
    breaches: list

    def __post_init__(self):
        for name in ("analysis_wall_seconds", "manual_prep_minutes", "human_active_seconds", "cleanup_seconds"):
            v = getattr(self, name)
            if not math.isfinite(float(v)):
                raise ValueError(f"{name} must be finite")
        if not isinstance(self.ceilings, dict):
            raise TypeError("ceilings must be a dict")
        if not isinstance(self.breaches, list):
            raise TypeError("breaches must be a list")

    @classmethod
    def from_dict(cls, d: dict) -> "ResourceReport":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Verdict:
    """verdict.json (spec B7, B8)."""
    schema_version: str
    pilot_seed: str
    gate_results: dict
    integrated: str
    failed_gates: list
    inconclusive_floors: list
    stopped_axes: list
    input_hashes: dict
    created_from_head: str

    def __post_init__(self):
        _check_enum(self.integrated, GATE_STATE, "integrated")
        if not isinstance(self.gate_results, dict):
            raise TypeError("gate_results must be a dict")
        for gate, res in self.gate_results.items():
            state = res.get("state") if isinstance(res, dict) else res
            _check_enum(state, GATE_STATE, f"gate_results[{gate}].state")
        for name in ("failed_gates", "inconclusive_floors", "stopped_axes"):
            if not isinstance(getattr(self, name), list):
                raise TypeError(f"{name} must be a list")

    @classmethod
    def from_dict(cls, d: dict) -> "Verdict":
        return strict_from_dict(cls, d)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)
